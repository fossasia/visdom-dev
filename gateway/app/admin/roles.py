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
    SUPPORT: {"User", "Workspace", "Membership", "APIKey", "WorkspaceInvite", "SharedLink"},
    SUPERADMIN: {"User", "Workspace", "Membership", "APIKey", "WorkspaceInvite", "SharedLink", "AdminUser"},
}


def can_see(role, model_name):
    return model_name in _VISIBLE.get(role, set())


def is_valid(role):
    return role in ROLES
