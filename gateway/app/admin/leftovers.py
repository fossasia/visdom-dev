# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Cleanup sections that are managed a row at a time.

Each is a list the janitor already finds, given a page of its own where rows
can be deleted one by one, a selection at a time, or all together. A new
section is a new entry in ``SECTIONS``.
"""

from dataclasses import dataclass
from typing import Callable

from app.admin import janitor


@dataclass(frozen=True)
class Leftover:
    model: str
    title: str
    subtitle: str
    explain: str
    consequence: str
    singular: str
    plural: str
    columns: tuple
    find: Callable
    cells: Callable
    label: Callable
    delete: Callable

    def count(self, n: int) -> str:
        return f"{n} {self.singular if n == 1 else self.plural}"


def _link_cells(link):
    summary = janitor.link_summary(link)
    return [summary["workspace"], summary["issued_to"], link.role or "member", summary["expired"]]


def _link_label(link):
    summary = janitor.link_summary(link)
    return f"the {summary['workspace']} link for {summary['issued_to']}"


def _invite_cells(invite):
    summary = janitor.invite_summary(invite)
    sent = invite.created_at.date().isoformat() if invite.created_at else ""
    return [summary["email"], summary["workspace"], invite.role or "member", sent]


SECTIONS = {
    "links": Leftover(
        model="SharedLink",
        title="Expired shared links",
        subtitle="Shared links past their expiry.",
        explain=(
            "An expired link no longer lets anyone join, so deleting one changes nothing for its "
            "workspace. It only drops the record of who was once sent it."
        ),
        consequence="This cannot be undone. The link already grants nothing.",
        singular="link",
        plural="links",
        columns=("Workspace", "Issued to", "Role", "Expired"),
        find=janitor.expired_links,
        cells=_link_cells,
        label=_link_label,
        delete=janitor.delete_expired_links,
    ),
    "invites": Leftover(
        model="WorkspaceInvite",
        title="Answered invites",
        subtitle="Invites to people who already signed up.",
        explain=(
            "Signing up turns pending invites into memberships, so these were left behind and can "
            "never be accepted. Deleting one leaves the person's account and memberships as they are."
        ),
        consequence="This cannot be undone. The person's account and memberships are not touched.",
        singular="invite",
        plural="invites",
        columns=("Email", "Workspace", "Role", "Sent"),
        find=janitor.answered_invites,
        cells=_invite_cells,
        label=lambda invite: f"the invite for {invite.email}",
        delete=janitor.delete_answered_invites,
    ),
}


def rows(db, leftover: Leftover):
    return [
        {"id": str(row.id), "cells": leftover.cells(row), "label": leftover.label(row)}
        for row in leftover.find(db)
    ]
