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
    ("update", "user", {"password_hash": "[redacted]"}, "a@x.io", "Changed account a@x.io: set a new password."),
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
]


@pytest.mark.parametrize("action,model,changes,subject,expected", CASES)
def test_each_kind_of_change_reads_as_a_sentence(action, model, changes, subject, expected):
    assert wording.sentence(action, model, changes, subject) == expected


@pytest.mark.parametrize("action,model,changes,subject,expected", CASES)
def test_no_sentence_shows_raw_values(action, model, changes, subject, expected):
    line = wording.sentence(action, model, changes, subject)
    for mark in ("{", "}", "_", "True", "False", "None"):
        assert mark not in line.replace(subject, "")


def test_an_unknown_kind_of_change_still_reads(admin=None):
    line = wording.sentence("update", "Gadget", {"shiny_level": 3}, "g1")
    assert line == "Changed Gadget g1: shiny level set to 3."
