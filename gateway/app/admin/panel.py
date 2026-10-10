# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""The staff admin panel, mounted on its own route with its own login."""

import functools
import logging
import os
import secrets
import time
import uuid

from sqladmin import Admin, BaseView, ModelView, expose
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy.orm import joinedload
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.admin import activity, janitor, roles
from app.admin.audit import StaffAuditBackend
from app.config import settings
from app.database import SessionLocal, engine
from app.models import (
    AdminAction,
    AdminUser,
    APIKey,
    APIKeyWorkspace,
    Membership,
    SharedLink,
    User,
    Workspace,
    WorkspaceInvite,
    utcnow,
)
from app.security import get_password_hash, verify_password

SESSION_KEY = "admin_user"
ROLE_KEY = "admin_role"
EMAIL_KEY = "admin_email"

DANGEROUS_ENVIRONMENTS = ("prod", "production", "live")


@functools.lru_cache(maxsize=1)
def _placeholder_hash():
    """A hash no password matches, checked when there is no account to check.

    Refusing an unknown email then costs the same as refusing a wrong password,
    so the time a sign-in takes does not say which emails are staff accounts.
    """
    return get_password_hash(secrets.token_urlsafe(32))


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
        finally:
            db.close()
        return True


class RoleScopedView(ModelView):
    """A view that hides itself from roles not allowed to see the model."""

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


class UserAdmin(ChangeableView, model=User):
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"
    column_list = [
        User.email,
        User.username,
        User.tier,
        User.is_active,
        User.created_at,
    ]
    column_searchable_list = [User.email, User.username]
    column_sortable_list = [User.email, User.tier, User.created_at]
    column_default_sort = (User.created_at, True)
    column_details_exclude_list = [User.password_hash]
    form_columns = [User.is_active, User.tier]


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
    entry = activity.cached_activity().get(str(model.id))
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
    entry = activity.cached_activity().get(str(model.id))
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
    entry = activity.cached_activity().get(str(model.id))
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


class WorkspaceAdmin(RoleScopedView, model=Workspace):
    name = "Workspace"
    name_plural = "Workspaces"
    icon = "fa-solid fa-folder"
    column_list = [
        Workspace.name,
        Workspace.slug,
        Workspace.creator,
        Workspace.created_at,
        "activity",
        "last_active",
        "size",
    ]
    column_labels = {
        Workspace.creator: "Created by",
        Workspace.created_at: "Created",
        "activity": "Active now",
        "last_active": "Last write",
        "size": "On disk",
    }
    column_formatters = {
        Workspace.creator: lambda m, a: _email_of(m.creator),
        Workspace.created_at: _workspace_created,
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
        "activity": _workspace_activity,
        "last_active": _workspace_last_active,
        "size": _workspace_size,
        "members": _member_lines,
        "invites": _invite_lines,
        "keys": _key_lines,
        "links": _link_lines,
    }


class MembershipAdmin(RoleScopedView, model=Membership):
    name = "Membership"
    name_plural = "Memberships"
    icon = "fa-solid fa-users"
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


class APIKeyAdmin(ChangeableView, model=APIKey):
    name = "API key"
    name_plural = "API keys"
    icon = "fa-solid fa-key"
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
    column_formatters = {APIKey.owner: lambda m, a: _email_of(m.owner)}
    column_details_exclude_list = [APIKey.hashed_key]
    column_sortable_list = [APIKey.created_at, APIKey.last_used_at]
    form_columns = [APIKey.is_active]


class WorkspaceInviteAdmin(RoleScopedView, model=WorkspaceInvite):
    name = "Invite"
    name_plural = "Invites"
    icon = "fa-solid fa-envelope"
    column_list = [
        WorkspaceInvite.email,
        WorkspaceInvite.workspace,
        WorkspaceInvite.role,
        WorkspaceInvite.created_at,
    ]
    column_labels = {WorkspaceInvite.workspace: "Workspace"}
    column_formatters = {WorkspaceInvite.workspace: lambda m, a: _slug_of(m.workspace)}
    column_searchable_list = [WorkspaceInvite.email]


class AdminUserAdmin(RoleScopedView, model=AdminUser):
    name = "Staff account"
    name_plural = "Staff accounts"
    icon = "fa-solid fa-user-shield"
    column_list = [
        AdminUser.email,
        AdminUser.role,
        AdminUser.is_active,
        AdminUser.created_at,
        AdminUser.last_login_at,
    ]
    column_details_exclude_list = [AdminUser.password_hash]


class JanitorView(BaseView):
    """Leftovers worth a look, on one page.

    Support and above only: it reads across every workspace at once, which is a
    wider view of other people's data than a viewer is given anywhere else.
    """

    name = "Cleanup"
    icon = "fa-solid fa-broom"
    template = "sqladmin/janitor.html"

    def is_visible(self, request: Request) -> bool:
        return self._allowed(request)

    def is_accessible(self, request: Request) -> bool:
        return self._allowed(request)

    @staticmethod
    def _allowed(request: Request) -> bool:
        return request.session.get(ROLE_KEY) in (roles.SUPPORT, roles.SUPERADMIN)

    @expose("/janitor", methods=["GET"])
    async def page(self, request: Request):
        if not self._allowed(request):
            return Response("Forbidden", status_code=403)
        return await self.templates.TemplateResponse(request, self.template)


def janitor_findings():
    """The cleanup sections, opened and closed around one render."""
    db = SessionLocal()
    try:
        return janitor.findings(db)
    finally:
        db.close()


class AdminActionAdmin(RoleScopedView, model=AdminAction):
    """What staff have changed, newest first.

    Read only, and deliberately not editable by anyone: a trail that can be
    rewritten by the people it describes is not a trail.
    """

    name = "Audit trail"
    name_plural = "Audit trail"
    icon = "fa-solid fa-clipboard-list"
    column_list = [
        AdminAction.created_at,
        AdminAction.admin_email,
        AdminAction.action,
        AdminAction.model,
        AdminAction.row_id,
        AdminAction.changes,
    ]
    column_labels = {
        AdminAction.created_at: "When",
        AdminAction.admin_email: "Who",
        AdminAction.action: "Did",
        AdminAction.model: "To",
        AdminAction.row_id: "Row",
        AdminAction.changes: "Set",
    }
    column_sortable_list = [AdminAction.created_at, AdminAction.admin_email]
    column_default_sort = (AdminAction.created_at, True)
    column_searchable_list = [AdminAction.admin_email, AdminAction.model]


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
    base = str(request.base_url).rstrip("/")
    cards = []
    db = SessionLocal()
    try:
        for label, model, slug in _CARDS:
            if not roles.can_see(role, model.__name__):
                continue
            cards.append({
                "label": label,
                "count": db.query(model).count(),
                "url": "%s/admin/%s/list" % (base, slug),
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


def mount_admin(app, secret_key, base_url="/admin"):
    """Attach the admin panel to a FastAPI app."""
    admin = Admin(
        app=app,
        engine=engine,
        base_url=base_url,
        title="Visdom Dev staff",
        templates_dir=os.path.join(os.path.dirname(__file__), "templates"),
        authentication_backend=StaffAuth(secret_key=secret_key, path=base_url),
        audit_backend=StaffAuditBackend(SessionLocal, SESSION_KEY, EMAIL_KEY),
    )
    admin.templates.env.globals["overview_cards"] = overview_cards
    admin.templates.env.globals["admin_environment"] = admin_environment
    admin.templates.env.globals["admin_identity"] = admin_identity
    admin.templates.env.globals["janitor_findings"] = janitor_findings
    admin.templates.env.globals["overview_recent"] = overview_recent
    for view in VIEWS:
        admin.add_view(view)
    admin.add_view(JanitorView)
    return admin
