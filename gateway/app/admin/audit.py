# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""
Records what staff change through the admin panel.

sqladmin already emits an entry for every create, update and delete it performs,
so this only has to say where those entries go and who made them. Note that the
entry is written in its own transaction, after the change has committed: a crash
in between loses the record rather than the change, so this is a trail for
answering "who did that", not a ledger the data depends on.
"""

from sqladmin.audit import DBAuditBackend

from app.models import AdminAction


class StaffAuditBackend(DBAuditBackend):
    """Writes each change into `admin_actions`, attributed to the staff account."""

    def __init__(self, session_maker, session_key, email_key):
        super().__init__(session_maker)
        self.session_key = session_key
        self.email_key = email_key

    async def log(self, entry, request):
        """Keep only what an edit actually changed, with what it was before.

        A form save hands over every field on the form, changed or not. Stored
        like that, an entry cannot say what happened, only what the record
        looked like afterwards. An edit that changed nothing is not recorded.
        """
        before = getattr(request.state, "audit_before", None)
        if entry.action == "update" and before is not None and entry.changes is not None:
            changed = {
                key: value
                for key, value in entry.changes.items()
                if key not in before or before[key] != value
            }
            if not changed:
                return
            was = {key: before[key] for key in changed if key in before and not _is_secret(key)}
            if was:
                changed["was"] = was
            entry.changes = changed
        await super().log(entry, request)

    async def get_actor(self, request):
        return request.session.get(self.session_key)

    def build_row(self, entry, actor, request):
        return AdminAction(
            admin_id=str(actor) if actor else None,
            admin_email=request.session.get(self.email_key),
            action=entry.action,
            model=entry.identity,
            row_id=str(entry.pk) if entry.pk is not None else None,
            changes=_serialisable(entry.changes),
            created_at=entry.timestamp,
        )


_SECRET_FIELDS = ("password", "password_hash", "hashed_key", "token", "secret")

_REDACTED = "[redacted]"


def _is_secret(key):
    return any(marker in key.lower() for marker in _SECRET_FIELDS)


def _serialisable(changes):
    """Coerce submitted values into something the JSON column will take.

    Form values arrive as whatever the field produced, including UUIDs, dates
    and model instances, none of which the driver can encode. Secrets are
    replaced rather than encoded, so the trail says a password was set without
    saying what it was.
    """
    if not changes:
        return None
    clean = {}
    for key, value in changes.items():
        if _is_secret(key):
            clean[key] = _REDACTED
        else:
            clean[key] = _plain(value)
    return clean


def _plain(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _REDACTED if _is_secret(str(key)) else _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return str(value)


def remember(request, data, model, is_created):
    """Note what a record held before a form save, for ``log`` to compare with."""
    state = getattr(request, "state", None)
    if state is None:
        return
    state.audit_before = None if is_created else {key: getattr(model, key, None) for key in data}
