# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""The staff admin panel, mounted on its own route with its own login."""

import base64
import functools
import logging
import os
import secrets
import time
import uuid
from typing import get_args
from urllib.parse import urlencode

import wtforms
from sqladmin import Admin, BaseView, ModelView, expose
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import func
from sqlalchemy.orm import joinedload, object_session
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app import billing, bypass
from app.admin import activity, janitor, permissions, roles, wording
from app.admin.audit import StaffAuditBackend, remember
from app.config import settings
from app.database import SessionLocal, engine
from app.models import (
    AdminAction,
    AdminUser,
    APIKey,
    APIKeyWorkspace,
    Membership,
    Plan,
    SharedLink,
    User,
    Workspace,
    WorkspaceInvite,
    utcnow,
)
from app.schemas.workspace import RoleLiteral
from app.security import get_password_hash, verify_password

SESSION_KEY = "admin_user"
ROLE_KEY = "admin_role"
EMAIL_KEY = "admin_email"

MIN_SET_PASSWORD = 12

DANGEROUS_ENVIRONMENTS = ("prod", "production", "live")


@functools.lru_cache(maxsize=1)
def _placeholder_hash():
    """A hash no password matches, checked when there is no account to check.

    Refusing an unknown email then costs the same as refusing a wrong password,
    so the time a sign-in takes does not say which emails are staff accounts.
    """
    return get_password_hash(secrets.token_urlsafe(32))


class StaffAuth(AuthenticationBackend):
    def __init__(self, secret_key, path="/admin"):
        super().__init__(secret_key=secret_key, https_only=settings.COOKIE_SECURE, path=path)

    async def login(self, request: Request) -> bool:
        form = await request.form()
        email = (form.get("username") or "").strip().lower()
        password = form.get("password") or ""
        db = SessionLocal()
        try:
            admin = db.query(AdminUser).filter(AdminUser.email == email).first()
            known = admin is not None and admin.is_active
            matches = verify_password(password, admin.password_hash if known else _placeholder_hash())
            if not (known and matches):
                logging.info("admin login refused for %s", email)
                return False
            admin.last_login_at = utcnow()
            db.commit()
            request.session.update(
                {SESSION_KEY: str(admin.id), ROLE_KEY: admin.role, EMAIL_KEY: admin.email}
            )
            logging.info("admin login for %s as %s", email, admin.role)
            return True
        finally:
            db.close()

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request):
        admin_id = request.session.get(SESSION_KEY)
        if not admin_id:
            return RedirectResponse(request.url_for("admin:login"), status_code=302)
        try:
            admin_key = uuid.UUID(str(admin_id))
        except ValueError:
            request.session.clear()
            return RedirectResponse(request.url_for("admin:login"), status_code=302)
        db = SessionLocal()
        try:
            admin = db.query(AdminUser).filter(AdminUser.id == admin_key).first()
            if admin is None or not admin.is_active:
                request.session.clear()
                return RedirectResponse(request.url_for("admin:login"), status_code=302)
            request.session[ROLE_KEY] = admin.role
            request.session[EMAIL_KEY] = admin.email
            request.session[permissions.GRANTS_KEY] = permissions.held_by(db, admin)
        finally:
            db.close()
        return True


class RoleScopedView(ModelView):
    """A view that hides itself from roles not allowed to see the model."""

    details_template = "sqladmin/record_details.html"
    can_create = False
    can_edit = False
    can_delete = False
    can_export = False
    page_size = 50

    def is_visible(self, request: Request) -> bool:
        return roles.can_see(request.session.get(ROLE_KEY), self.model.__name__)

    def is_accessible(self, request: Request) -> bool:
        return roles.can_see(request.session.get(ROLE_KEY), self.model.__name__)


class ChangeableView(RoleScopedView):
    """A view whose rows a sufficiently privileged role may also change.

    Nothing here can be created or deleted. A staff member stopping an account
    or a key is undoing something reversible, and a deleted row takes its own
    audit trail with it.
    """

    can_edit = True

    async def check_can_edit(self, request: Request, model) -> bool:
        """The real gate. `can_edit` is a class attribute, so it cannot vary by
        role; sqladmin calls this per request, which is what makes the hidden
        button and the typed URL agree."""
        return roles.can_change(request.session.get(ROLE_KEY), self.model.__name__)

    async def on_model_change(
        self, data: dict, model, is_created: bool, request: Request
    ) -> None:
        """Drop any field this role is not allowed to set.

        The form is the same for every role that can edit at all, because
        sqladmin builds it without knowing the request. So the field level rule
        is applied to what was submitted instead, which also covers a request
        that never came from the form.
        """
        remember(request, data, model, is_created)
        allowed = roles.editable_fields(
            request.session.get(ROLE_KEY), self.model.__name__
        )
        refused = [
            key
            for key, value in data.items()
            if key not in allowed and value != getattr(model, key, None)
        ]
        if refused:
            raise HTTPException(
                status_code=403,
                detail=f"Your role cannot change: {', '.join(sorted(refused))}.",
            )
        for key in list(data):
            if key not in allowed:
                data.pop(key)


def _to_the_minute(field, empty=""):
    """A list column showing a moment to the minute.

    Seconds, microseconds and the offset are noise in a table someone is
    scanning, and on a narrow screen two full timestamps are enough to push the
    last columns out of the card.
    """

    def render(model, _attr):
        value = getattr(model, field, None)
        return value.strftime("%Y-%m-%d %H:%M") if value else empty

    return render


def _tier_choices():
    """Every plan, marked when it is hidden or archived.

    Archived plans are offered so an account already on one still shows its
    plan; moving an account onto one is refused when the form is saved.
    """
    db = SessionLocal()
    try:
        plans = db.query(Plan).order_by(Plan.sort_order, Plan.id).all()
    finally:
        db.close()

    def label(plan):
        if plan.archived_at is not None:
            return f"{plan.name} (archived)"
        if not plan.is_public:
            return f"{plan.name} (hidden)"
        return plan.name

    return [(plan.id, label(plan)) for plan in plans]


class UserAdmin(ChangeableView, model=User):
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"
    category = "People"
    category_icon = "fa-solid fa-users"
    column_list = [
        User.email,
        User.username,
        User.tier,
        User.bypass_limits,
        User.is_active,
        User.created_at,
        User.last_login_at,
    ]
    column_labels = {User.bypass_limits: "Limits bypassed"}
    column_searchable_list = [User.email, User.username]
    column_sortable_list = [
        User.email,
        User.tier,
        User.created_at,
        User.last_login_at,
    ]
    column_default_sort = (User.created_at, True)
    column_details_exclude_list = [User.password_hash]
    column_formatters = {
        User.created_at: _to_the_minute("created_at"),
        User.last_login_at: _to_the_minute("last_login_at", "never"),
        User.bypass_limits: lambda model, _attr: "bypassed" if model.bypass_limits else "",
    }
    form_columns = [User.is_active, User.tier, User.bypass_limits, User.password_hash]
    form_include_pk = True
    form_overrides = {"tier": wtforms.SelectField, "password_hash": wtforms.PasswordField}
    form_args = {
        "tier": {"label": "Plan", "choices": lambda: _tier_choices()},
        "bypass_limits": {
            "label": "Bypass plan limits",
            "description": "Superadmins only. Lifts every plan limit for this account until switched off.",
        },
        "password_hash": {
            "label": "Set a new password",
            "description": (
                f"Superadmins only, for an account locked out while email is not set up. "
                f"At least {MIN_SET_PASSWORD} characters. Leave blank to keep the current "
                f"one; setting one signs the account out everywhere."
            ),
            "validators": [
                wtforms.validators.Optional(),
                wtforms.validators.Length(min=MIN_SET_PASSWORD),
            ],
        },
    }

    async def scaffold_form(self, rules=None):
        """Make the password field optional, which its column cannot say.

        ``password_hash`` is not nullable, so sqladmin gives it a required
        validator, and every ordinary save of an account would then demand a
        new password before it would go through.
        """
        form = await super().scaffold_form(rules)
        field = form.password_hash
        field.kwargs["validators"] = [
            rule
            for rule in field.kwargs.get("validators", [])
            if not isinstance(rule, wtforms.validators.InputRequired)
        ]
        return form

    async def on_model_change(
        self, data: dict, model, is_created: bool, request: Request
    ) -> None:
        """Hash a submitted password before the role check sees it.

        The field is empty on every ordinary save, so a blank one is dropped
        rather than refused or written over the current hash. A submitted one is
        hashed here, the only place the plaintext exists, and bumps
        ``token_version`` so the sessions the old password opened are closed.
        """
        submitted = data.get("password_hash") or ""
        chosen = submitted if submitted.strip() else ""
        if not chosen:
            data.pop("password_hash", None)
        await super().on_model_change(data, model, is_created, request)
        if chosen:
            data["password_hash"] = get_password_hash(chosen)
            model.token_version = (model.token_version or 0) + 1
        tier = data.get("tier")
        if tier is None or tier == model.tier:
            return
        db = SessionLocal()
        try:
            allowed = billing.assignable(db, tier)
        finally:
            db.close()
        if not allowed:
            raise HTTPException(
                status_code=400,
                detail=f"{tier} is archived or does not exist, so no account can be put on it.",
            )


def _email_of(user):
    return user.email if user is not None else "unknown"


def _slug_of(workspace):
    return workspace.slug if workspace is not None else "unknown"


def _workspace_activity(model, name):
    """Render one workspace's live socket counts for the list view.

    Reads the fan-out's answer rather than the database: "active" here means
    someone is connected to the workspace right now, which only the visdom
    instances know.
    """
    entry = activity.known_activity().get(str(model.id))
    if entry is None:
        return "idle"
    viewers, writers = entry.get("viewers", 0), entry.get("writers", 0)
    if not viewers and not writers:
        return "idle"
    parts = []
    if viewers:
        parts.append(f"{viewers} reading")
    if writers:
        parts.append(f"{writers} writing")
    return ", ".join(parts)


def _workspace_last_active(model, name):
    """Render how long ago the workspace was last written to."""
    entry = activity.known_activity().get(str(model.id))
    last = entry.get("last_active_at") if entry else None
    if not last:
        return "unknown"
    seconds = max(0, int(time.time() - last))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def _member_lines(model, name):
    """Members and their roles, so the page answers who is actually in here.

    These read the database directly rather than walking relationships. sqladmin
    closes its session before the formatters run, so a lazy load here raises
    DetachedInstanceError, and eager loading through the view would still leave
    the second hop (a membership's user) detached.
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(Membership)
            .options(joinedload(Membership.user))
            .filter(Membership.workspace_id == model.id)
            .all()
        )
        if not rows:
            return "no members"
        rows.sort(key=lambda m: (m.role, _email_of(m.user)))
        return ", ".join(
            f"{_email_of(m.user)} ({m.role}"
            f"{'' if m.status == 'active' else ', ' + m.status})"
            for m in rows
        )
    finally:
        db.close()


def _invite_lines(model, name):
    db = SessionLocal()
    try:
        rows = (
            db.query(WorkspaceInvite)
            .filter(WorkspaceInvite.workspace_id == model.id)
            .all()
        )
        return ", ".join(f"{i.email} ({i.role})" for i in rows) or "none"
    finally:
        db.close()


def _key_lines(model, name):
    """Only keys bound to this workspace.

    An org scoped key works everywhere, so listing those would name every key
    its owner holds and say nothing about this workspace in particular.
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(APIKey)
            .join(APIKeyWorkspace, APIKeyWorkspace.api_key_id == APIKey.id)
            .options(joinedload(APIKey.owner))
            .filter(APIKeyWorkspace.workspace_id == model.id)
            .all()
        )
        return ", ".join(f"{k.name} ({_email_of(k.owner)})" for k in rows) or "none"
    finally:
        db.close()


def _for_roles_that_see(model_name, formatter):
    def format(model, name, request):
        if not roles.can_see(request.session.get(ROLE_KEY), model_name):
            return "hidden"
        return formatter(model, name)

    return format


def _link_lines(model, name):
    db = SessionLocal()
    try:
        rows = db.query(SharedLink).filter(SharedLink.workspace_id == model.id).all()
        return (
            ", ".join(
                f"{link.role}"
                f"{' for ' + link.invite_email if link.invite_email else ''}"
                for link in rows
            )
            or "none"
        )
    finally:
        db.close()


def _workspace_size(model, name):
    """Render how much disk a workspace is using.

    Worth showing because nothing limits it. Image plots are base64 and orders
    of magnitude heavier than line plots, so one account can fill the volume
    without doing anything obviously wrong, and this is the only place that
    would show it before the disk filled.
    """
    entry = activity.known_activity().get(str(model.id))
    size = entry.get("bytes") if entry else None
    if size is None:
        return "unknown"
    if size < 1024:
        return f"{size} B"
    for unit in ("KB", "MB", "GB"):
        size /= 1024.0
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"


def _workspace_created(model, name):
    """Workspaces created before the created_at column existed have no true age."""
    return model.created_at.strftime("%Y-%m-%d %H:%M") if model.created_at else "unknown"


def _workspace_standing(model, name):
    return "active" if model.is_active else "suspended"


class WorkspaceAdmin(ChangeableView, model=Workspace):
    name = "Workspace"
    name_plural = "Workspaces"
    icon = "fa-solid fa-folder"
    category = "Workspaces"
    category_icon = "fa-solid fa-folder"
    form_columns = [Workspace.is_active]
    column_list = [
        Workspace.name,
        Workspace.slug,
        Workspace.creator,
        Workspace.created_at,
        "standing",
        "activity",
        "last_active",
        "size",
    ]
    column_labels = {
        Workspace.creator: "Created by",
        Workspace.created_at: "Created",
        "standing": "Standing",
        "activity": "Active now",
        "last_active": "Last write",
        "size": "On disk",
    }
    column_formatters = {
        Workspace.creator: lambda m, a: _email_of(m.creator),
        Workspace.created_at: _workspace_created,
        "standing": _workspace_standing,
        "activity": _workspace_activity,
        "last_active": _workspace_last_active,
        "size": _workspace_size,
    }
    column_searchable_list = [Workspace.name, Workspace.slug]
    column_sortable_list = [Workspace.name, Workspace.slug, Workspace.created_at]
    column_default_sort = (Workspace.created_at, True)
    column_details_list = [
        Workspace.name,
        Workspace.slug,
        Workspace.creator,
        Workspace.created_at,
        "standing",
        "activity",
        "last_active",
        "size",
        "members",
        "invites",
        "keys",
        "links",
    ]
    column_labels_detail = {
        Workspace.creator: "Created by",
        Workspace.created_at: "Created",
        "standing": "Standing",
        "activity": "Active now",
        "last_active": "Last write",
        "size": "On disk",
        "members": "Members",
        "invites": "Pending email invites",
        "keys": "Keys bound to this workspace",
        "links": "Shared links",
    }
    column_formatters_detail = {
        Workspace.creator: lambda m, a: _email_of(m.creator),
        Workspace.created_at: _workspace_created,
        "standing": _workspace_standing,
        "activity": _workspace_activity,
        "last_active": _workspace_last_active,
        "size": _workspace_size,
        "members": _member_lines,
        "invites": _for_roles_that_see("WorkspaceInvite", _invite_lines),
        "keys": _for_roles_that_see("APIKey", _key_lines),
        "links": _for_roles_that_see("WorkspaceInvite", _link_lines),
    }

    async def list(self, request: Request):
        await activity.refresh_activity()
        return await super().list(request)

    async def get_object_for_details(self, request: Request):
        await activity.refresh_activity()
        return await super().get_object_for_details(request)


def _other_active_admins(db, membership):
    """Active admins of the same workspace other than this member.

    Locked while it is read, because the answer is being used to decide whether
    this member may stop being an admin. Two staff demoting the last two admins
    at once would otherwise each see the other and both be allowed through,
    leaving a workspace nobody can administer.
    """
    admins = (
        db.query(Membership)
        .filter(
            Membership.workspace_id == membership.workspace_id,
            Membership.role == "admin",
            Membership.status == "active",
        )
        .order_by(Membership.user_id)
        .with_for_update()
        .all()
    )
    return [admin for admin in admins if admin.user_id != membership.user_id]


class MembershipAdmin(ChangeableView, model=Membership):
    """Who belongs to a workspace, and what they may do there.

    The only place staff can change someone's access without also changing
    their account. Read as: the workspace keeps working afterwards, which is
    what the two guards below are for.
    """

    name = "Membership"
    name_plural = "Memberships"
    icon = "fa-solid fa-users"
    category = "Workspaces"
    category_icon = "fa-solid fa-folder"
    form_columns = [Membership.role]
    form_overrides = {"role": wtforms.SelectField}
    form_args = {"role": {"choices": [(role, role) for role in get_args(RoleLiteral)]}}
    column_list = [
        Membership.workspace,
        Membership.user,
        Membership.role,
        Membership.status,
    ]
    column_labels = {Membership.workspace: "Workspace", Membership.user: "Member"}
    column_formatters = {
        Membership.workspace: lambda m, a: _slug_of(m.workspace),
        Membership.user: lambda m, a: _email_of(m.user),
    }
    column_sortable_list = [Membership.role, Membership.status]

    @property
    def can_delete(self) -> bool:
        """Advertised for everyone; refused per request by ``check_can_delete``.

        sqladmin reads this off the class without a request in hand, so it
        cannot vary by role here. The gate is the per-request check below, which
        is what makes the hidden button and the typed URL agree.
        """
        return True

    async def check_can_delete(self, request: Request, model) -> bool:
        return roles.can_remove(request.session.get(ROLE_KEY), "Membership")

    async def on_model_change(
        self, data: dict, model, is_created: bool, request: Request
    ) -> None:
        """Apply the field rules, then refuse a change that orphans a workspace.

        The owner's role is fixed, matching what the API already refuses. That
        rule is what guarantees a workspace always has an admin, so the console
        cannot be the one place it does not hold.
        """
        await super().on_model_change(data, model, is_created, request)
        new_role = data.get("role")
        if new_role is None or new_role == model.role or model.role != "admin":
            return

        db = object_session(model)
        workspace = db.query(Workspace).filter(Workspace.id == model.workspace_id).first()
        if workspace is not None and workspace.created_by == model.user_id:
            raise HTTPException(
                status_code=403,
                detail="The workspace owner is always an admin.",
            )
        if not _other_active_admins(db, model):
            raise HTTPException(
                status_code=400,
                detail="This is the workspace's last admin.",
            )

    async def on_model_delete(self, model, request: Request) -> None:
        """Refuse a removal that would leave a workspace with no admin.

        The same rule the API applies when a member removes another. A console
        that could do what the product refuses would be a way around the rule
        rather than a way to administer it.
        """
        db = object_session(model)
        if model.role == "admin" and model.status == "active" and not _other_active_admins(db, model):
            raise HTTPException(
                status_code=400,
                detail="Cannot remove the last admin of a workspace.",
            )
        workspace = db.query(Workspace).filter(Workspace.id == model.workspace_id).first()
        if workspace is not None and workspace.created_by == model.user_id:
            raise HTTPException(
                status_code=403,
                detail="The workspace owner cannot be removed.",
            )


class APIKeyAdmin(ChangeableView, model=APIKey):
    name = "API key"
    name_plural = "API keys"
    icon = "fa-solid fa-key"
    category = "Access"
    category_icon = "fa-solid fa-key"
    column_list = [
        APIKey.name,
        APIKey.prefix,
        APIKey.scope,
        APIKey.is_active,
        APIKey.owner,
        APIKey.created_at,
        APIKey.last_used_at,
    ]
    column_labels = {APIKey.owner: "Owner", APIKey.last_used_at: "Last used"}
    column_formatters = {
        APIKey.owner: lambda m, a: _email_of(m.owner),
        APIKey.created_at: _to_the_minute("created_at"),
        APIKey.last_used_at: _to_the_minute("last_used_at", "never"),
    }
    column_details_exclude_list = [APIKey.hashed_key]
    column_sortable_list = [APIKey.created_at, APIKey.last_used_at]
    form_columns = [APIKey.is_active]


class WorkspaceInviteAdmin(RoleScopedView, model=WorkspaceInvite):
    name = "Invite"
    name_plural = "Invites"
    icon = "fa-solid fa-envelope"
    category = "Access"
    category_icon = "fa-solid fa-key"
    column_list = [
        WorkspaceInvite.email,
        WorkspaceInvite.workspace,
        WorkspaceInvite.role,
        WorkspaceInvite.created_at,
    ]
    column_labels = {WorkspaceInvite.workspace: "Workspace"}
    column_formatters = {
        WorkspaceInvite.workspace: lambda m, a: _slug_of(m.workspace),
        WorkspaceInvite.created_at: _to_the_minute("created_at"),
    }
    column_searchable_list = [WorkspaceInvite.email]


def _other_active_superadmins(db, admin):
    """Superadmins other than this one who can still sign in.

    Locked while it is read, for the same reason the workspace admin check is:
    two staff stopping the last two superadmins at once would each see the
    other and both be let through, leaving a console nobody can open.
    """
    superadmins = (
        db.query(AdminUser)
        .filter(
            AdminUser.role == roles.SUPERADMIN,
            AdminUser.is_active.is_(True),
        )
        .order_by(AdminUser.id)
        .with_for_update()
        .all()
    )
    return [other for other in superadmins if other.id != admin.id]




class AdminUserAdmin(RoleScopedView, model=AdminUser):
    """Staff accounts, and the one thing in the panel staff may create.

    Until now the only way to add a colleague was to open a shell on the box
    that serves production and run `app.admin.bootstrap`. Granting someone a
    read only console role therefore meant granting them the machine first,
    which is a far larger thing than the role being handed over.
    """

    name = "Staff account"
    name_plural = "Staff accounts"
    icon = "fa-solid fa-user-shield"
    category = "People"
    category_icon = "fa-solid fa-users"
    can_create = True
    can_edit = True
    column_list = [
        AdminUser.email,
        AdminUser.role,
        AdminUser.is_active,
        AdminUser.created_at,
        AdminUser.last_login_at,
    ]
    column_formatters = {
        AdminUser.created_at: _to_the_minute("created_at"),
        AdminUser.last_login_at: _to_the_minute("last_login_at", "never"),
    }
    column_details_exclude_list = [AdminUser.password_hash]
    form_columns = [
        AdminUser.email,
        AdminUser.role,
        AdminUser.password_hash,
        AdminUser.is_active,
    ]
    form_create_rules = ["email", "role", "password_hash"]
    form_edit_rules = ["is_active"]
    form_overrides = {"role": wtforms.SelectField, "password_hash": wtforms.PasswordField}
    form_args = {
        "email": {"validators": [wtforms.validators.Email()]},
        "role": {"choices": [(name, name) for name in roles.ROLES]},
        "password_hash": {
            "label": "Password",
            "description": f"At least {MIN_SET_PASSWORD} characters. Shown to nobody after this.",
            "validators": [wtforms.validators.Length(min=MIN_SET_PASSWORD)],
        },
    }

    async def check_can_create(self, request: Request) -> bool:
        """The real gate, for the same reason `check_can_edit` is one: the class
        attribute cannot vary by role, and sqladmin calls this per request."""
        return roles.can_add(request.session.get(ROLE_KEY), self.model.__name__)

    async def check_can_edit(self, request: Request, model) -> bool:
        return roles.can_change(request.session.get(ROLE_KEY), self.model.__name__)

    async def on_model_change(
        self, data: dict, model, is_created: bool, request: Request
    ) -> None:
        """Creating checks the whole form. Editing may only stop an account."""
        remember(request, data, model, is_created)
        role = request.session.get(ROLE_KEY)
        if not is_created:
            self._check_edit(data, model, role)
            return

        if not roles.can_add(role, self.model.__name__):
            raise HTTPException(status_code=403, detail="Your role cannot add staff.")

        data["email"] = (data.get("email") or "").strip().lower()
        if not data["email"]:
            raise HTTPException(status_code=400, detail="An email is required.")

        if data.get("role") not in roles.ROLES:
            raise HTTPException(
                status_code=400,
                detail="Role must be one of: %s." % ", ".join(roles.ROLES),
            )

        password = data.get("password_hash") or ""
        if len(password) < MIN_SET_PASSWORD:
            raise HTTPException(
                status_code=400,
                detail=f"The password must be at least {MIN_SET_PASSWORD} characters.",
            )
        data["password_hash"] = get_password_hash(password)

        db = SessionLocal()
        try:
            taken = (
                db.query(AdminUser).filter(AdminUser.email == data["email"]).first()
            )
        finally:
            db.close()
        if taken is not None:
            raise HTTPException(
                status_code=400,
                detail="A staff account already exists for that email.",
            )

    def _check_edit(self, data, model, role):
        """Drop anything but the fields this role may set, then hold the line
        that at least one superadmin is left able to sign in.

        A panel that can lock everyone out of itself is a panel whose recovery
        is a shell on the box, which is the thing this view exists to avoid.
        """
        allowed = roles.editable_fields(role, self.model.__name__)
        refused = [
            key
            for key, value in data.items()
            if key not in allowed and value != getattr(model, key, None)
        ]
        if refused:
            raise HTTPException(
                status_code=403,
                detail=f"Your role cannot change: {', '.join(sorted(refused))}.",
            )
        for key in list(data):
            if key not in allowed:
                data.pop(key)

        if data.get("is_active") is False and model.role == roles.SUPERADMIN:
            if not _other_active_superadmins(object_session(model), model):
                raise HTTPException(
                    status_code=400,
                    detail="This is the last superadmin who can still sign in.",
                )


class PermissionsView(BaseView):
    """Handing a superadmin's own powers to admins, one at a time.

    Superadmin only, always. A grant goes to every admin or to one by name,
    takes effect on that person's next page, and is recorded like any other
    change.
    """

    name = "Permissions"
    icon = "fa-solid fa-key"
    category = "People"
    category_icon = "fa-solid fa-users"

    def is_visible(self, request: Request) -> bool:
        return self._allowed(request)

    def is_accessible(self, request: Request) -> bool:
        return self._allowed(request)

    @staticmethod
    def _allowed(request: Request) -> bool:
        return request.session.get(ROLE_KEY) == roles.SUPERADMIN

    @expose("/permissions", methods=["GET", "POST"])
    async def permissions_page(self, request: Request):
        if not self._allowed(request):
            return Response("Forbidden", status_code=403)

        db = SessionLocal()
        try:
            if request.method == "POST":
                form = await request.form()
                group = set(form.getlist("group"))
                single = {tuple(value.split("|", 1)) for value in form.getlist("single") if "|" in value}
                changed = permissions.save(db, group, single, request.session.get(EMAIL_KEY))
            else:
                changed = None
            standing = permissions.table(db)
            admins = [{"id": str(admin.id), "email": admin.email} for admin in standing["admins"]]
        finally:
            db.close()

        if changed is not None:
            for change in changed:
                label = permissions.GRANTABLE[change["permission"]][0]
                _record_action(
                    request, "update", "StaffGrant", change["permission"],
                    {"granted": change["granted"], "permission": label, "to": change["to"]},
                )
            count = len(changed)
            message = (
                f"Saved {count} change{'' if count == 1 else 's'}." if count else "Nothing was changed."
            )
            query = urlencode({"notice": message, "notice_kind": "success" if count else "info"})
            return RedirectResponse(request.url.replace(query=query), status_code=303)

        return await self.templates.TemplateResponse(
            request,
            "sqladmin/permissions.html",
            {
                "grantable": [
                    {"key": key, "label": label, "about": about}
                    for key, (label, about) in permissions.GRANTABLE.items()
                ],
                "admins": admins,
                "group": standing["group"],
                "single": standing["single"],
            },
        )


class LimitBypassView(BaseView):
    """Bypassing plan limits, for one account or for every account at once.

    One account is a decision about one customer and can also be made on that
    account's own form. Every account is a promotion: it reaches accounts that
    register later too, and it removes the storage ceilings for the whole
    platform. Either way it hands out what the plans hold back, so the page is
    for superadmins only.

    Both are switches rather than plan changes on purpose. Nothing about any
    account's plan is touched, so switching off puts back exactly what was
    there, with no list of who was on what to restore.
    """

    name = "Limit bypass"
    icon = "fa-solid fa-unlock"
    category = "Billing"
    category_icon = "fa-solid fa-layer-group"

    def is_visible(self, request: Request) -> bool:
        return self._allowed(request)

    def is_accessible(self, request: Request) -> bool:
        return self._allowed(request)

    @staticmethod
    def _allowed(request: Request) -> bool:
        return roles.can_bypass_limits(request.session.get(ROLE_KEY))

    @expose("/limit-bypass", methods=["GET", "POST"])
    async def limit_bypass(self, request: Request):
        """Show what is bypassed, and switch it.

        The role check is load bearing, as on the cleanup page: sqladmin applies
        ``is_accessible`` to the menu entry and not to an exposed route.
        """
        if not self._allowed(request):
            return Response("Forbidden", status_code=403)

        if request.method == "POST":
            kind, message = await self._act(request)
            query = urlencode({"notice": message, "notice_kind": kind})
            return RedirectResponse(request.url.replace(query=query), status_code=303)

        db = SessionLocal()
        try:
            switch = bypass.standing(db)
            everyone = {
                "on": bool(switch is not None and switch.is_on),
                "changed_by": switch.changed_by if switch is not None else None,
                "changed_at": (
                    switch.changed_at.strftime("%Y-%m-%d %H:%M")
                    if switch is not None and switch.changed_at
                    else None
                ),
            }
            accounts = [
                {"id": str(user.id), "email": user.email, "plan": user.tier or billing.DEFAULT_TIER}
                for user in bypass.accounts(db)
            ]
            total = db.query(User).count()
        finally:
            db.close()
        return await self.templates.TemplateResponse(
            request,
            "sqladmin/limit_bypass.html",
            {
                "everyone": everyone,
                "accounts": accounts,
                "total": total,
            },
        )

    async def _act(self, request: Request):
        form = await request.form()
        intent = str(form.get("intent") or "")
        if intent in ("everyone_on", "everyone_off"):
            return self._switch_everyone(request, intent == "everyone_on")
        if intent == "account_on":
            return self._switch_account(request, True, email=str(form.get("email") or ""))
        if intent == "account_off":
            return self._switch_account(request, False, user_id=str(form.get("user_id") or ""))
        return "error", "Nothing was changed."

    @staticmethod
    def _switch_everyone(request: Request, on: bool):
        db = SessionLocal()
        try:
            changed = bypass.set_for_everyone(db, on, by=request.session.get(EMAIL_KEY))
        finally:
            db.close()
        if not changed:
            return "info", "That was already %s." % ("on" if on else "off")
        _record_action(request, "update", "PlatformSwitch", bypass.EVERYONE, {"is_on": on})
        if on:
            return "success", "Plan limits are now bypassed for every account."
        return "success", "Every account is back on its plan's limits."

    @staticmethod
    def _switch_account(request: Request, on: bool, email: str = "", user_id: str = ""):
        db = SessionLocal()
        try:
            user = None
            if email.strip():
                wanted = email.strip().lower()
                user = db.query(User).filter(func.lower(User.email) == wanted).first()
            elif user_id:
                try:
                    user = db.get(User, uuid.UUID(user_id))
                except ValueError:
                    user = None
            if user is None:
                return "error", "No account matches that."
            found_id, found_email = str(user.id), user.email
            changed = bypass.set_for_account(db, user, on)
        finally:
            db.close()
        if not changed:
            return "info", "%s was already %s." % (found_email, "bypassed" if on else "on its plan's limits")
        _record_action(request, "update", "User", found_id, {"bypass_limits": on})
        if on:
            return "success", f"Plan limits are now bypassed for {found_email}."
        return "success", f"{found_email} is back on its plan's limits."


class JanitorView(BaseView):
    """Leftovers worth a look, on one page.

    Support and above only: it reads across every workspace at once, which is a
    wider view of other people's data than a viewer is given anywhere else.
    """

    name = "Cleanup"
    icon = "fa-solid fa-broom"
    category = "Operations"
    category_icon = "fa-solid fa-screwdriver-wrench"
    template = "sqladmin/janitor.html"

    def is_visible(self, request: Request) -> bool:
        return self._allowed(request)

    def is_accessible(self, request: Request) -> bool:
        return self._allowed(request)

    @staticmethod
    def _allowed(request: Request) -> bool:
        return roles.can_sweep(request.session.get(ROLE_KEY))

    @expose("/janitor", methods=["GET"])
    async def page(self, request: Request):
        if not self._allowed(request):
            return Response("Forbidden", status_code=403)
        return await self.templates.TemplateResponse(request, self.template)


def _record_action(request, action, model, row_id, changes):
    """Write the audit entry for a change made outside sqladmin's forms.

    sqladmin records what it changes through a form, but the cleanup page's
    actions are not form saves, so the trail is written here or they would be
    the changes in the panel that leave no record. A failure to log is not
    allowed to fail the request: the change is already made, and losing the
    record is better than reporting an error for work that was done.
    """
    db = SessionLocal()
    try:
        db.add(
            AdminAction(
                admin_id=request.session.get(SESSION_KEY),
                admin_email=request.session.get(EMAIL_KEY),
                action=action,
                model=model,
                row_id=str(row_id),
                changes=changes,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logging.exception("could not record a %s on %s in the audit trail", action, model)
    finally:
        db.close()


def janitor_findings():
    """The cleanup sections, opened and closed around one render."""
    db = SessionLocal()
    try:
        return janitor.findings(db)
    finally:
        db.close()


_AUDIT_LABELS = {
    "user": (User, lambda row: row.email),
    "workspace": (Workspace, lambda row: row.slug),
    "apikey": (APIKey, lambda row: f"{row.name} ({_email_of(row.owner)})"),
    "adminuser": (AdminUser, lambda row: row.email),
}


def _audit_kind(entry):
    return "".join(ch for ch in str(entry.model).lower() if ch.isalnum())


def _audit_key(entry):
    kind = _audit_kind(entry)
    try:
        if kind == "membership":
            user_id, _, workspace_id = entry.row_id.partition(";")
            return kind, (uuid.UUID(user_id), uuid.UUID(workspace_id))
        if kind in _AUDIT_LABELS:
            return kind, uuid.UUID(entry.row_id)
    except (TypeError, ValueError):
        pass
    return None


def _audit_labels(db, entries):
    wanted = {}
    for entry in entries:
        key = _audit_key(entry)
        if key is not None:
            wanted.setdefault(key[0], set()).add(key[1])
    labels = {}
    for kind, ids in wanted.items():
        if kind == "membership":
            rows = (
                db.query(Membership)
                .options(joinedload(Membership.user), joinedload(Membership.workspace))
                .filter(
                    Membership.user_id.in_({user_id for user_id, _ in ids}),
                    Membership.workspace_id.in_({workspace_id for _, workspace_id in ids}),
                )
            )
            for row in rows:
                pair = (row.user_id, row.workspace_id)
                if pair in ids:
                    labels[(kind, pair)] = _RECORD_LABELS["Membership"](row)
        else:
            table, label = _AUDIT_LABELS[kind]
            rows = db.query(table).filter(table.id.in_(ids))
            if table is APIKey:
                rows = rows.options(joinedload(APIKey.owner))
            for row in rows:
                labels[(kind, row.id)] = label(row)
    return labels


def _audit_subject(model, name):
    """Name the row an entry is about, falling back to its id.

    An entry outlives what it describes, which is the point of keeping one, so
    a row that has since been deleted still has to render.
    """
    if not model.row_id:
        return "unknown"
    kind = _audit_kind(model)
    if kind not in _AUDIT_LABELS and kind != "membership":
        return model.row_id
    labels = getattr(model, "_audit_labels", None)
    if labels is None:
        db = SessionLocal()
        try:
            labels = _audit_labels(db, [model])
        except Exception:
            logging.exception("could not name the subject of an audit entry")
            return model.row_id
        finally:
            db.close()
    label = labels.get(_audit_key(model))
    if label is not None:
        return label

    changes = model.changes or {}
    email, username = changes.get("email"), changes.get("username")
    named = f"{email} ({username})" if email and username else email or username
    deleting = str(model.action or "").lower() == "delete"
    if named:
        return named if deleting else f"{named} (deleted)"
    if kind == "user":
        return "(name not recorded)" if deleting else "(deleted, name not recorded)"
    return f"{model.row_id} (deleted)"


def _audit_sentence(model, name):
    """What happened, as one line a person can read."""
    return wording.sentence(model.action, model.model, model.changes, _audit_subject(model, name))


def _audit_when(model, name):
    return model.created_at.strftime("%Y-%m-%d %H:%M:%S") if model.created_at else ""


def _audit_who(model, name):
    return model.admin_email or "automatic"


class AdminActionAdmin(RoleScopedView, model=AdminAction):
    """What staff have changed, newest first.

    Read only, and deliberately not editable by anyone: a trail that can be
    rewritten by the people it describes is not a trail.
    """

    name = "Audit trail"
    name_plural = "Audit trail"
    icon = "fa-solid fa-clipboard-list"
    category = "Operations"
    category_icon = "fa-solid fa-screwdriver-wrench"
    def is_visible(self, request: Request) -> bool:
        return permissions.has(request, permissions.SEE_AUDIT)

    def is_accessible(self, request: Request) -> bool:
        return permissions.has(request, permissions.SEE_AUDIT)

    column_list = [AdminAction.created_at, AdminAction.admin_email, "what"]
    column_labels = {
        AdminAction.created_at: "When (UTC)",
        AdminAction.admin_email: "Who",
        "what": "What happened",
        AdminAction.action: "Kind of change",
        AdminAction.model: "Kind of record",
        AdminAction.row_id: "Record",
        AdminAction.changes: "Stored values",
    }
    column_formatters = {
        "what": _audit_sentence,
        AdminAction.admin_email: _audit_who,
        AdminAction.created_at: _audit_when,
    }
    column_details_list = [
        AdminAction.created_at,
        AdminAction.admin_email,
        "what",
        AdminAction.action,
        AdminAction.model,
        AdminAction.row_id,
        AdminAction.changes,
    ]
    column_formatters_detail = {
        "what": _audit_sentence,
        AdminAction.admin_email: _audit_who,
        AdminAction.row_id: _audit_subject,
        AdminAction.created_at: _audit_when,
    }
    column_sortable_list = [AdminAction.created_at, AdminAction.admin_email]
    column_default_sort = (AdminAction.created_at, True)
    column_searchable_list = [AdminAction.admin_email, AdminAction.model]

    async def list(self, request: Request):
        page = await super().list(request)
        db = SessionLocal()
        try:
            labels = _audit_labels(db, page.rows)
        except Exception:
            logging.exception("could not name the subjects of the audit trail")
            labels = None
        finally:
            db.close()
        if labels is not None:
            for row in page.rows:
                row._audit_labels = labels
        return page


VIEWS = (
    UserAdmin,
    WorkspaceAdmin,
    MembershipAdmin,
    APIKeyAdmin,
    WorkspaceInviteAdmin,
    AdminUserAdmin,
    AdminActionAdmin,
)


_CARDS = (
    ("Users", User, "user"),
    ("Workspaces", Workspace, "workspace"),
    ("Memberships", Membership, "membership"),
    ("API keys", APIKey, "api-key"),
    ("Staff", AdminUser, "admin-user"),
)


def overview_cards(request):
    """Counts for the models the signed-in role is allowed to see."""
    role = request.session.get(ROLE_KEY)
    cards = []
    db = SessionLocal()
    try:
        for label, model, slug in _CARDS:
            if not roles.can_see(role, model.__name__):
                continue
            cards.append({
                "label": label,
                "count": db.query(model).count(),
                "url": str(request.url_for("admin:list", identity=slug)),
            })
    except Exception as exc:
        logging.warning("overview counts failed: %s", exc)
    finally:
        db.close()
    return cards


def overview_recent(request, limit=5):
    """The newest accounts, for roles allowed to see users."""
    if not roles.can_see(request.session.get(ROLE_KEY), "User"):
        return []
    db = SessionLocal()
    try:
        rows = db.query(User).order_by(User.created_at.desc()).limit(limit).all()
        return [
            {
                "email": u.email,
                "tier": u.tier,
                "joined": u.created_at.strftime("%Y-%m-%d") if u.created_at else "",
            }
            for u in rows
        ]
    except Exception as exc:
        logging.warning("overview recent failed: %s", exc)
        return []
    finally:
        db.close()


def admin_environment():
    """Which deployment this panel is attached to, for the banner.

    Two panels that look identical are a hazard as soon as one of them is
    production, and more so once the write actions land. Unset shows no banner
    rather than a wrong one.
    """
    name = (settings.ADMIN_ENVIRONMENT or "").strip()
    return {"name": name, "danger": name.lower() in DANGEROUS_ENVIRONMENTS}


def admin_identity(request):
    """Who is signed in and with what role.

    The role decides what the panel will show at all, so the answer to "why can
    I not see that" belongs on screen rather than being found by hitting a 403.
    """
    return {
        "email": request.session.get(EMAIL_KEY),
        "role": request.session.get(ROLE_KEY, ""),
    }


def overview_attention(request):
    """Cleanup sections that have something in them, for roles allowed to look.

    None says the role may not look, which is a different answer from an empty
    list saying there is nothing to find, and keeps the policy here rather than
    in the template.
    """
    if not roles.can_sweep(request.session.get(ROLE_KEY)):
        return None
    try:
        return [section for section in janitor_findings() if section["rows"]]
    except Exception as exc:
        logging.warning("overview attention failed: %s", exc)
        return []


_RECORD_LABELS = {
    "User": lambda row: row.email,
    "Workspace": lambda row: row.slug,
    "APIKey": lambda row: f"{row.name} ({_email_of(row.owner)})",
    "AdminUser": lambda row: row.email,
    "Membership": lambda row: "%s in %s" % (
        _email_of(row.user),
        row.workspace.slug if row.workspace else "?",
    ),
    "WorkspaceInvite": lambda row: row.email,
}


def record_label(model_view, model):
    """What to call the row a detail page is about.

    The topbar says which record its actions would apply to, so the name has to
    be the one a person would recognise rather than a primary key. A model
    without an entry falls back to its id, which is worse to read but never
    wrong.
    """
    label = _RECORD_LABELS.get(type(model).__name__)
    if label is None:
        return str(getattr(model, "id", ""))
    try:
        return label(model)
    except Exception:
        return str(getattr(model, "id", ""))


def _janitor_url(admin, request):
    """Where the cleanup page lives, asked of the view rather than guessed.

    sqladmin names a custom view's route after the exposed function, so the
    name is `view-page` here and would change with the method. Reading it off
    the registered view keeps that detail out of the templates.
    """
    return _view_url(admin, request, JanitorView)


def _view_url(admin, request, kind):
    for view in admin._views:
        if isinstance(view, kind):
            return request.url_for(f"admin:view-{view.identity}")
    return None


def limits_bypassed_for_everyone():
    """Whether the switch for every account is on, for the marker in the header.

    A promotion is easy to start and easy to forget, and while it runs nothing
    holds storage back. So it is said on every page of the panel rather than
    only on the page that switches it.
    """
    db = SessionLocal()
    try:
        return bypass.for_everyone(db)
    except Exception as exc:
        logging.warning("could not read the limit bypass switch: %s", exc)
        return False
    finally:
        db.close()


def _creatables(admin, request):
    """The views this role may add a row to, for the New menu.

    Empty is the normal answer today. Everything the panel shows is created by
    someone using the product, so the menu stays hidden until something here is
    genuinely ours to make.
    """
    items = []
    for view in admin._views:
        if not getattr(view, "is_model", False) or not view.can_create:
            continue
        if not view.is_accessible(request) or not view.is_visible(request):
            continue
        items.append({
            "label": view.name,
            "icon": view.icon,
            "url": request.url_for("admin:create", identity=view.identity),
        })
    return items


def _favicon_data_uri():
    """The visdom mark, inlined so the panel needs no static route for it.

    The console frontend serves the same file, but the panel is reachable
    without it and should not lose its icon when it is. Under a kilobyte, so
    inlining costs less than the plumbing would.
    """
    path = os.path.join(os.path.dirname(__file__), "static", "favicon.svg")
    try:
        with open(path, "rb") as handle:
            encoded = base64.b64encode(handle.read()).decode("ascii")
    except OSError as exc:
        logging.warning("admin favicon missing: %s", exc)
        return ""
    return f"data:image/svg+xml;base64,{encoded}"


def mount_admin(app, secret_key, base_url="/admin"):
    """Attach the admin panel to a FastAPI app."""
    admin = Admin(
        app=app,
        engine=engine,
        base_url=base_url,
        title="Visdom Dev staff",
        favicon_url=_favicon_data_uri(),
        templates_dir=os.path.join(os.path.dirname(__file__), "templates"),
        authentication_backend=StaffAuth(secret_key=secret_key, path=base_url),
        audit_backend=StaffAuditBackend(SessionLocal, SESSION_KEY, EMAIL_KEY),
    )
    admin.templates.env.globals["overview_cards"] = overview_cards
    admin.templates.env.globals["admin_environment"] = admin_environment
    admin.templates.env.globals["admin_identity"] = admin_identity
    admin.templates.env.globals["janitor_findings"] = janitor_findings
    admin.templates.env.globals["overview_recent"] = overview_recent
    admin.templates.env.globals["overview_attention"] = overview_attention
    admin.templates.env.globals["admin_creatables"] = (
        lambda request: _creatables(admin, request)
    )
    admin.templates.env.globals["janitor_url"] = (
        lambda request: _janitor_url(admin, request)
    )
    admin.templates.env.globals["record_label"] = record_label
    admin.templates.env.globals["limits_bypassed_for_everyone"] = limits_bypassed_for_everyone
    admin.templates.env.globals["limit_bypass_url"] = lambda request: (
        _view_url(admin, request, LimitBypassView)
        if roles.can_bypass_limits(request.session.get(ROLE_KEY))
        else None
    )
    for view in VIEWS:
        admin.add_view(view)
    admin.add_view(PermissionsView)
    admin.add_view(LimitBypassView)
    admin.add_view(JanitorView)
    return admin
