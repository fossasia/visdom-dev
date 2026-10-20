# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Turning an audit entry into a sentence a person can read.

An entry is stored as an action, a kind of record and the values that were
set, which is the right shape to keep and the wrong one to read: nobody should
have to decode ``{"is_active": false}`` to learn that an account was suspended.
The stored entry is left as it is. This only decides how it is shown.
"""

KINDS = {
    "user": "account",
    "workspace": "workspace",
    "apikey": "API key",
    "membership": "membership",
    "adminuser": "staff account",
    "workspaceinvite": "invite",
    "staffgrant": "permission",
}

FIELDS = {
    "is_active": "active",
    "tier": "plan",
    "role": "role",
    "password_hash": "password",
    "email": "email",
}

_HIDDEN = {"was", "email"}


def kind_of(model) -> str:
    key = "".join(ch for ch in str(model or "").lower() if ch.isalnum())
    return KINDS.get(key, str(model or "record"))


def _key(model) -> str:
    return "".join(ch for ch in str(model or "").lower() if ch.isalnum())


def _plain(value) -> str:
    if value is None or value == "":
        return "nothing"
    if value is True:
        return "yes"
    if value is False:
        return "no"
    if isinstance(value, dict):
        return ", ".join(f"{FIELDS.get(k, k)} {_plain(v)}" for k, v in value.items()) or "nothing"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or "nothing"
    return str(value)


def _others(changes: dict, done: set, was: dict) -> str:
    parts = []
    for field, value in changes.items():
        if field in done or field in _HIDDEN:
            continue
        label = FIELDS.get(field, field.replace("_", " "))
        if field == "password_hash":
            parts.append("set a new password")
        elif field in was:
            parts.append(f"{label} changed from {_plain(was[field])} to {_plain(value)}")
        else:
            parts.append(f"{label} set to {_plain(value)}")
    return "; ".join(parts)


def sentence(action, model, changes, subject) -> str:
    """One readable line for an audit entry."""
    changes = dict(changes or {})
    was = changes.get("was") if isinstance(changes.get("was"), dict) else {}
    key = _key(model)
    kind = kind_of(model)
    subject = subject or "unknown"
    verb = str(action or "").lower()
    done = set()
    lead = None

    if verb in ("create", "insert", "add"):
        lead = f"Added {kind} {subject}"
        if key == "adminuser" and changes.get("role"):
            lead += f" as {changes['role']}"
            done.add("role")
        done.update({"id", "is_active", "password_hash"})
    elif verb == "delete":
        return f"Deleted {kind} {subject}."
    elif key == "user":
        if "tier" in changes:
            source = was.get("tier")
            lead = (
                f"Moved account {subject} from the {source} plan to {changes['tier']}"
                if source
                else f"Put account {subject} on the {changes['tier']} plan"
            )
            done.add("tier")
        elif "is_active" in changes:
            lead = f"Switched account {subject} back on" if changes["is_active"] else f"Suspended account {subject}"
            done.add("is_active")
    elif key == "workspace":
        if "is_active" in changes:
            lead = f"Switched workspace {subject} back on" if changes["is_active"] else f"Suspended workspace {subject}"
            done.add("is_active")
    elif key == "apikey":
        if changes.get("is_active") is False:
            lead = f"Revoked API key {subject}"
            done.add("is_active")
        elif changes.get("is_active") is True:
            lead = f"Switched API key {subject} back on"
            done.add("is_active")
    elif key == "membership" and "role" in changes:
        lead = f"Changed {subject} to {changes['role']}"
        done.add("role")
    elif key == "staffgrant" and "granted" in changes:
        what = str(changes.get("permission", subject))
        what = what[:1].lower() + what[1:]
        who = changes.get("to", "someone")
        if changes["granted"]:
            return f"Gave {who} permission to {what}."
        return f"Took away from {who} the permission to {what}."

    rest = _others(changes, done, was)
    if lead is None:
        return f"Changed {kind} {subject}: {rest}." if rest else f"Saved {kind} {subject} with no changes."
    return f"{lead}; {rest}." if rest else f"{lead}."
