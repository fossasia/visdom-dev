# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Who may see what in the admin panel.

Reading every user's data is itself a privilege, so the role decides which
models are visible rather than only which actions are allowed. Write
permissions attach to these same roles when actions are added.
"""

VIEWER = "viewer"
SUPPORT = "support"
SUPERADMIN = "superadmin"

ROLES = (VIEWER, SUPPORT, SUPERADMIN)

_VISIBLE = {
    VIEWER: {"User", "Workspace", "Membership"},
    SUPPORT: {
        "User",
        "Workspace",
        "Membership",
        "APIKey",
        "WorkspaceInvite",
        "AdminAction",
    },
    SUPERADMIN: {
        "User",
        "Workspace",
        "Membership",
        "APIKey",
        "WorkspaceInvite",
        "AdminUser",
        "AdminAction",
    },
}


_CHANGEABLE = {
    VIEWER: set(),
    SUPPORT: {"APIKey", "User"},
    SUPERADMIN: {"APIKey", "User"},
}

_EDITABLE_FIELDS = {
    SUPPORT: {"APIKey": {"is_active"}, "User": {"is_active"}},
    SUPERADMIN: {"APIKey": {"is_active"}, "User": {"is_active", "tier"}},
}


def can_see(role, model_name):
    return model_name in _VISIBLE.get(role, set())


def can_change(role, model_name):
    return model_name in _CHANGEABLE.get(role, set())


def editable_fields(role, model_name):
    """The fields this role may set on this model, empty when it may not."""
    return _EDITABLE_FIELDS.get(role, {}).get(model_name, set())


def is_valid(role):
    return role in ROLES
