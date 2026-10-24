# Copyright 2017-present, The Visdom Authors
"""The staff role ladder.

Viewer only reads, support handles the day to day incident, admin decides what
a customer is entitled to, and superadmin decides who has console access at
all. These assert the boundaries between them rather than the plumbing that
enforces them.
"""
from app.admin import roles


def test_there_are_four_roles_in_increasing_privilege():
    assert roles.ROLES == (roles.VIEWER, roles.SUPPORT, roles.ADMIN, roles.SUPERADMIN)


def test_a_viewer_only_reads():
    assert roles.is_valid("viewer")
    for model in ("User", "Workspace", "Membership"):
        assert roles.can_see(roles.VIEWER, model)
        assert not roles.can_change(roles.VIEWER, model)
        assert not roles.can_remove(roles.VIEWER, model)
    assert not roles.can_see(roles.VIEWER, "APIKey")


def test_only_a_superadmin_sees_staff_accounts():
    assert not roles.can_see(roles.SUPPORT, "AdminUser")
    assert not roles.can_see(roles.ADMIN, "AdminUser")
    assert roles.can_see(roles.SUPERADMIN, "AdminUser")


def test_only_a_superadmin_hands_out_console_access():
    assert not roles.can_add(roles.SUPPORT, "AdminUser")
    assert not roles.can_add(roles.ADMIN, "AdminUser")
    assert roles.can_add(roles.SUPERADMIN, "AdminUser")


def test_an_admin_cannot_change_a_staff_account():
    assert not roles.can_change(roles.ADMIN, "AdminUser")
    assert roles.editable_fields(roles.ADMIN, "AdminUser") == set()


def test_support_reads_the_same_records_as_an_admin():
    for model in ("User", "Workspace", "Membership", "APIKey"):
        assert roles.can_see(roles.SUPPORT, model)
        assert roles.can_see(roles.ADMIN, model)


def test_only_a_superadmin_reads_the_audit_trail():
    assert roles.can_see(roles.SUPERADMIN, "AdminAction")
    assert not roles.can_see(roles.ADMIN, "AdminAction")
    assert not roles.can_see(roles.SUPPORT, "AdminAction")


def test_setting_a_tier_is_an_entitlement_decision():
    assert roles.editable_fields(roles.SUPPORT, "User") == {"is_active"}
    assert roles.editable_fields(roles.ADMIN, "User") == {"is_active", "tier"}
    assert roles.editable_fields(roles.SUPERADMIN, "User") == {
        "is_active",
        "tier",
        "password_hash",
        "bypass_limits",
    }


def test_support_and_above_may_suspend_a_workspace():
    for role in (roles.SUPPORT, roles.ADMIN, roles.SUPERADMIN):
        assert roles.editable_fields(role, "Workspace") == {"is_active"}


def test_removing_a_membership_starts_at_admin():
    assert not roles.can_remove(roles.SUPPORT, "Membership")
    assert roles.can_remove(roles.ADMIN, "Membership")
    assert roles.can_remove(roles.SUPERADMIN, "Membership")


def test_only_a_superadmin_may_set_someones_password():
    assert "password_hash" not in roles.editable_fields(roles.SUPPORT, "User")
    assert "password_hash" not in roles.editable_fields(roles.ADMIN, "User")
    assert "password_hash" in roles.editable_fields(roles.SUPERADMIN, "User")


def test_every_role_but_a_viewer_may_open_the_cleanup_page():
    assert not roles.can_sweep(roles.VIEWER)
    for role in (roles.SUPPORT, roles.ADMIN, roles.SUPERADMIN):
        assert roles.can_sweep(role)


def test_an_unknown_role_is_refused_everywhere():
    assert not roles.is_valid("stranger")
    assert not roles.can_see("stranger", "User")
    assert not roles.can_change("stranger", "User")
    assert not roles.can_add("stranger", "AdminUser")
    assert not roles.can_remove("stranger", "Membership")
    assert not roles.can_sweep("stranger")
    assert roles.editable_fields("stranger", "User") == set()


def test_no_role_may_act_on_a_model_it_cannot_see():
    """Acting on a record implies reading it, so the tables must not disagree."""
    for role in roles.ROLES:
        for table in (roles._CHANGEABLE, roles._REMOVABLE, roles._ADDABLE):
            for model in table[role]:
                assert roles.can_see(role, model), f"{role} may act on unseen {model}"
        for model in roles._EDITABLE_FIELDS.get(role, {}):
            assert roles.can_change(role, model), f"{role} has fields on unchangeable {model}"


def test_privilege_only_grows_up_the_ladder():
    """Each role may see at least everything the role below it may see."""
    for lower, higher in zip(roles.ROLES, roles.ROLES[1:], strict=False):
        assert roles._VISIBLE[lower] <= roles._VISIBLE[higher]
        assert roles._CHANGEABLE[lower] <= roles._CHANGEABLE[higher]
        assert roles._REMOVABLE[lower] <= roles._REMOVABLE[higher]
        assert roles._ADDABLE[lower] <= roles._ADDABLE[higher]

