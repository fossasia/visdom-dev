# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Things only a superadmin may do, and handing some of them to admins.

The three roles decide most of what a staff member can see and change, and
that stays fixed. A few things sit with the superadmin alone. Each of those
can be granted here, to every admin at once or to one admin by name, without
making anybody a superadmin.

Granting is itself never grantable, and neither is managing staff accounts:
either one would let an admin hand themselves everything else.
"""

import uuid

from sqlalchemy.orm import Session

from app.admin import roles
from app.models import AdminUser, StaffGrant, utcnow

SEE_AUDIT = "see_audit"
TRASH_ACCOUNTS = "trash_accounts"
DELETE_ACCOUNTS = "delete_accounts"

GRANTABLE = {
    SEE_AUDIT: ("See the audit trail", "Read who changed what, and when."),
    TRASH_ACCOUNTS: (
        "Trash and restore accounts",
        "Move accounts to the trash and take them back out. Nothing is deleted.",
    ),
    DELETE_ACCOUNTS: (
        "Delete accounts for good",
        "Remove trashed accounts with their workspaces and plots. Cannot be undone.",
    ),
}

GRANTS_KEY = "admin_grants"


def held_by(db: Session, admin: AdminUser) -> list[str]:
    """What this staff account has been granted, by name or through its role."""
    if admin.role != roles.ADMIN:
        return []
    rows = (
        db.query(StaffGrant.permission)
        .filter((StaffGrant.admin_user_id == admin.id) | (StaffGrant.role == roles.ADMIN))
        .all()
    )
    return sorted({row[0] for row in rows if row[0] in GRANTABLE})


def has(request, permission: str) -> bool:
    """Whether the signed-in staff member may do this."""
    from app.admin.panel import ROLE_KEY

    if request.session.get(ROLE_KEY) == roles.SUPERADMIN:
        return True
    return permission in (request.session.get(GRANTS_KEY) or [])


def table(db: Session) -> dict:
    """Every grant as it stands: which the admin group holds, and which each admin holds."""
    admins = (
        db.query(AdminUser)
        .filter(AdminUser.role == roles.ADMIN, AdminUser.is_active.is_(True))
        .order_by(AdminUser.email)
        .all()
    )
    group, single = set(), set()
    for grant in db.query(StaffGrant).all():
        if grant.role == roles.ADMIN:
            group.add(grant.permission)
        elif grant.admin_user_id is not None:
            single.add((grant.permission, str(grant.admin_user_id)))
    return {"admins": admins, "group": group, "single": single}


def save(db: Session, group: set, single: set, by: str | None) -> list[dict]:
    """Make the stored grants match what was ticked. Returns what changed."""
    now = table(db)
    known = {str(admin.id): admin.email for admin in now["admins"]}
    group = {p for p in group if p in GRANTABLE}
    single = {(p, a) for p, a in single if p in GRANTABLE and a in known}
    changed = []

    for permission in sorted(group - now["group"]):
        db.add(StaffGrant(permission=permission, role=roles.ADMIN, granted_by=by, granted_at=utcnow()))
        changed.append({"granted": True, "permission": permission, "to": "every admin"})
    for permission in sorted(now["group"] - group):
        db.query(StaffGrant).filter(
            StaffGrant.permission == permission, StaffGrant.role == roles.ADMIN
        ).delete(synchronize_session=False)
        changed.append({"granted": False, "permission": permission, "to": "every admin"})

    for permission, admin_id in sorted(single - now["single"]):
        db.add(
            StaffGrant(
                permission=permission,
                admin_user_id=uuid.UUID(admin_id),
                granted_by=by,
                granted_at=utcnow(),
            )
        )
        changed.append({"granted": True, "permission": permission, "to": known[admin_id]})
    for permission, admin_id in sorted(now["single"] - single):
        if admin_id not in known:
            continue
        db.query(StaffGrant).filter(
            StaffGrant.permission == permission, StaffGrant.admin_user_id == uuid.UUID(admin_id)
        ).delete(synchronize_session=False)
        changed.append({"granted": False, "permission": permission, "to": known[admin_id]})

    db.commit()
    return changed
