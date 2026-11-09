# Copyright 2017-present, The Visdom Authors
"""Audit entries read as sentences.

The stored entry is values and field names, which nobody should have to decode.
Each kind of change the console makes is pinned to the line a person sees.
"""

import pytest

from app.admin import wording

CASES = [
    ("update", "user", {"is_active": False, "was": {"is_active": True}}, "a@x.io", "Suspended account a@x.io."),
    ("update", "user", {"is_active": True}, "a@x.io", "Switched account a@x.io back on."),
    (
        "update",
        "user",
        {"tier": "pro", "was": {"tier": "free"}},
        "a@x.io",
        "Moved account a@x.io from the free plan to pro.",
    ),
    (
        "update",
        "User",
        {"tier": "pro", "moved_from": "free", "moved_in_bulk": True},
        "a@x.io",
        "Moved account a@x.io from the free plan to pro.",
    ),
    ("update", "User", {"trashed": True, "email": "a@x.io"}, "a@x.io", "Moved account a@x.io to the trash."),
    ("update", "User", {"trashed": False, "email": "a@x.io"}, "a@x.io", "Restored account a@x.io from the trash."),
    ("update", "user", {"password_hash": "[redacted]"}, "a@x.io", "Changed account a@x.io: set a new password."),
    (
        "delete",
        "User",
        {
            "reason": "deleted from the trash by staff",
            "email": "a@x.io",
            "workspaces_removed": ["lab"],
            "bytes_freed": 0,
        },
        "gone",
        "Deleted account a@x.io for good (deleted from the trash by staff), with its workspace lab.",
    ),
    ("edit", "Workspace", {"is_active": False}, "vision", "Suspended workspace vision."),
    ("edit", "Workspace", {"is_active": True}, "vision", "Switched workspace vision back on."),
    ("update", "APIKey", {"is_active": False}, "training (a@x.io)", "Revoked API key training (a@x.io)."),
    (
        "update",
        "Membership",
        {"role": "viewer", "was": {"role": "member"}},
        "a@x.io in lab",
        "Changed a@x.io in lab to viewer.",
    ),
    ("delete", "Membership", {}, "a@x.io in lab", "Deleted membership a@x.io in lab."),
    (
        "update",
        "APIKey",
        {"is_active": False, "revoked_from": "cleanup"},
        "training (a@x.io)",
        "Revoked API key training (a@x.io) from the cleanup page.",
    ),
    (
        "update",
        "APIKey",
        {"is_active": False, "revoked_from": "notice period ended"},
        "training (a@x.io)",
        "Revoked API key training (a@x.io) (notice period ended).",
    ),
    (
        "update",
        "APIKey",
        {"revoke_after_days": 30},
        "training (a@x.io)",
        "Warned the owner of API key training (a@x.io) that it will be revoked in 30 days.",
    ),
    (
        "create",
        "admin-user",
        {"email": "s@x.io", "role": "support", "is_active": True},
        "s@x.io",
        "Added staff account s@x.io as support.",
    ),
    (
        "update",
        "StaffGrant",
        {"granted": True, "permission": "See the audit trail", "to": "every admin"},
        "see_audit",
        "Gave every admin permission to see the audit trail.",
    ),
    ("update", "PlatformSwitch", {"is_on": True}, "bypass_limits", "Switched the limit bypass on for every account."),
    (
        "update",
        "plan",
        {"price": 39, "limits": {"workspaces": 20, "members": None}, "was": {"price": 29}},
        "pro",
        "Changed plan pro: price changed from 29 to 39; limits set to workspaces 20, members unlimited.",
    ),
    (
        "delete",
        "SharedLink",
        {"deleted_from": "cleanup"},
        "vision",
        "Deleted shared link vision from the cleanup page.",
    ),
]


@pytest.mark.parametrize("action,model,changes,subject,expected", CASES)
def test_each_kind_of_change_reads_as_a_sentence(action, model, changes, subject, expected):
    assert wording.sentence(action, model, changes, subject) == expected


@pytest.mark.parametrize("action,model,changes,subject,expected", CASES)
def test_no_sentence_shows_raw_values(action, model, changes, subject, expected):
    line = wording.sentence(action, model, changes, subject)
    for mark in ("{", "}", "_", "True", "False", "None"):
        assert mark not in line.replace(subject, "").replace("bypass_limits", "")


def test_an_unknown_kind_of_change_still_reads(admin=None):
    line = wording.sentence("update", "Gadget", {"shiny_level": 3}, "g1")
    assert line == "Changed Gadget g1: shiny level set to 3."
