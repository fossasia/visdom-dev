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
    "plan": "plan",
    "sharedlink": "shared link",
    "workspaceinvite": "invite",
    "platformswitch": "platform switch",
    "staffgrant": "permission",
}

FIELDS = {
    "is_active": "active",
    "tier": "plan",
    "role": "role",
    "name": "name",
    "price": "price",
    "sort_order": "position in lists",
    "is_public": "public",
    "archived_at": "archived",
    "limits": "limits",
    "features": "features",
    "retention_days": "days of history kept",
    "password_hash": "password",
    "bypass_limits": "limit bypass",
    "email": "email",
}

_HIDDEN = {"was", "email", "moved_in_bulk", "moved_from", "revoked_from", "deleted_from", "reason"}


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


def _limits(value) -> str:
    if not isinstance(value, dict):
        return _plain(value)
    return ", ".join(f"{k.replace('_', ' ')} {'unlimited' if v is None else v}" for k, v in value.items())


def _others(changes: dict, done: set, was: dict) -> str:
    parts = []
    for field, value in changes.items():
        if field in done or field in _HIDDEN:
            continue
        label = FIELDS.get(field, field.replace("_", " "))
        if field == "password_hash":
            parts.append("set a new password")
        elif field == "limits":
            parts.append(f"limits set to {_limits(value)}")
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
        if key == "user":
            email, username = changes.get("email"), changes.get("username")
            named = f"{email} ({username})" if email and username else email or subject
            lead = f"Deleted account {named} for good"
            if changes.get("reason"):
                lead += f" ({changes['reason']})"
            removed = changes.get("workspaces_removed") or []
            if removed:
                lead += f", with its workspace{'' if len(removed) == 1 else 's'} {', '.join(removed)}"
            return lead + "."
        lead = f"Deleted {kind} {subject}"
        if changes.get("deleted_from"):
            lead += f" from the {changes['deleted_from']} page"
        return lead + "."
    elif key == "user":
        if "trashed" in changes:
            lead = (
                f"Moved account {subject} to the trash"
                if changes["trashed"]
                else f"Restored account {subject} from the trash"
            )
            done.add("trashed")
        elif "tier" in changes:
            source = changes.get("moved_from", was.get("tier"))
            lead = (
                f"Moved account {subject} from the {source} plan to {changes['tier']}"
                if source
                else f"Put account {subject} on the {changes['tier']} plan"
            )
            done.add("tier")
        elif "bypass_limits" in changes:
            lead = (
                f"Switched the limit bypass on for account {subject}"
                if changes["bypass_limits"]
                else f"Switched the limit bypass off for account {subject}"
            )
            done.add("bypass_limits")
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
            source = changes.get("revoked_from")
            if source == "cleanup":
                lead += " from the cleanup page"
            elif source:
                lead += f" ({source})"
            done.add("is_active")
        elif changes.get("is_active") is True:
            lead = f"Switched API key {subject} back on"
            done.add("is_active")
        elif "revoke_after_days" in changes:
            days = changes["revoke_after_days"]
            lead = f"Warned the owner of API key {subject} that it will be revoked in {days} days"
            done.add("revoke_after_days")
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
    elif key == "platformswitch" and "is_on" in changes:
        lead = (
            "Switched the limit bypass on for every account"
            if changes["is_on"]
            else "Switched the limit bypass off for every account"
        )
        done.add("is_on")

    rest = _others(changes, done, was)
    if lead is None:
        return f"Changed {kind} {subject}: {rest}." if rest else f"Saved {kind} {subject} with no changes."
    return f"{lead}; {rest}." if rest else f"{lead}."
