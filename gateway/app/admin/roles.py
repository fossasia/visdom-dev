# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Who may see and do what in the admin panel.

Four roles, in increasing privilege: viewer only reads, support handles the day
to day incident, admin decides what a customer is entitled to, and superadmin
decides who has console access at all.

Reading every user's data is itself a privilege, so the role decides which
models are visible rather than only which actions are allowed. Visibility,
change, removal and creation are answered separately, and a role that may
change a model is restricted again to the fields it may set. That separation is
what keeps "suspend an account" from also meaning "edit an account".
"""

VIEWER = "viewer"
SUPPORT = "support"
ADMIN = "admin"
SUPERADMIN = "superadmin"

ROLES = (VIEWER, SUPPORT, ADMIN, SUPERADMIN)

_SUPPORT_VISIBLE = {
    "User",
    "Workspace",
    "Membership",
    "APIKey",
    "WorkspaceInvite",
}

_VISIBLE = {
    VIEWER: {"User", "Workspace", "Membership"},
    SUPPORT: _SUPPORT_VISIBLE,
    ADMIN: _SUPPORT_VISIBLE,
    SUPERADMIN: _SUPPORT_VISIBLE | {"AdminUser", "AdminAction"},
}

_CHANGEABLE = {
    VIEWER: set(),
    SUPPORT: {"APIKey", "User", "Workspace", "Membership"},
    ADMIN: {"APIKey", "User", "Workspace", "Membership"},
    SUPERADMIN: {"APIKey", "User", "Workspace", "Membership", "AdminUser"},
}

_REMOVABLE = {
    VIEWER: set(),
    SUPPORT: set(),
    ADMIN: {"Membership"},
    SUPERADMIN: {"Membership"},
}

_ADDABLE = {
    VIEWER: set(),
    SUPPORT: set(),
    ADMIN: set(),
    SUPERADMIN: {"AdminUser"},
}

_ENTITLEMENT_FIELDS = {
    "APIKey": {"is_active"},
    "User": {"is_active", "tier"},
    "Workspace": {"is_active"},
    "Membership": {"role"},
}

_EDITABLE_FIELDS = {
    SUPPORT: {
        "APIKey": {"is_active"},
        "User": {"is_active"},
        "Workspace": {"is_active"},
        "Membership": {"role"},
    },
    ADMIN: _ENTITLEMENT_FIELDS,
    SUPERADMIN: dict(
        _ENTITLEMENT_FIELDS,
        User=_ENTITLEMENT_FIELDS["User"] | {"password_hash", "bypass_limits"},
        AdminUser={"is_active"},
    ),
}

_SWEEPERS = {SUPPORT, ADMIN, SUPERADMIN}


def can_see(role, model_name):
    return model_name in _VISIBLE.get(role, set())


def can_change(role, model_name):
    return model_name in _CHANGEABLE.get(role, set())


def editable_fields(role, model_name):
    """The fields this role may set on this model, empty when it may not."""
    return _EDITABLE_FIELDS.get(role, {}).get(model_name, set())


def can_add(role, model_name):
    """Whether this role may create a row of this model."""
    return model_name in _ADDABLE.get(role, set())


def can_remove(role, model_name):
    """Whether this role may delete a row of this model outright."""
    return model_name in _REMOVABLE.get(role, set())


def can_sweep(role):
    """Whether this role may open the cleanup page.

    It reads across every workspace at once, so it is answered here rather than
    by a tuple spelled out at each call site.
    """
    return role in _SWEEPERS


def can_bypass_limits(role):
    """Whether this role may bypass plan limits, for one account or for all.

    A bypass hands out everything a plan holds back, storage included, so it
    sits with superadmins only.
    """
    return "bypass_limits" in editable_fields(role, "User")


def is_valid(role):
    return role in ROLES
