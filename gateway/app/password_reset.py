# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Single-use links for choosing a new password.

Only a SHA-256 of each token is stored, so a copy of the table cannot be turned
into working links. A link lasts an hour and is spent by its first use. Using
one also spends every other link the account still holds and signs out all of
its sessions. An account is sent at most a few links an hour, so the form
cannot be used to flood someone's inbox.
"""

import datetime
import hashlib
import secrets

from app.models import PasswordReset, User, utcnow
from app.security import get_password_hash

LINK_MINUTES = 60
PER_HOUR = 3


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue(db, user: User, now: datetime.datetime | None = None) -> str | None:
    """A new token for ``user``, or None when they have had ``PER_HOUR`` this hour."""
    now = now or utcnow()
    db.query(PasswordReset).filter(PasswordReset.expires_at < now - datetime.timedelta(days=1)).delete(
        synchronize_session=False
    )
    recent = (
        db.query(PasswordReset)
        .filter(PasswordReset.user_id == user.id, PasswordReset.created_at > now - datetime.timedelta(hours=1))
        .count()
    )
    if recent >= PER_HOUR:
        db.commit()
        return None
    token = secrets.token_urlsafe(32)
    db.add(
        PasswordReset(
            user_id=user.id,
            token_hash=_digest(token),
            created_at=now,
            expires_at=now + datetime.timedelta(minutes=LINK_MINUTES),
        )
    )
    db.commit()
    return token


def spend_all(db, user: User, now: datetime.datetime | None = None) -> None:
    """Mark every link this account still holds as used, without committing."""
    db.query(PasswordReset).filter(
        PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)
    ).update({PasswordReset.used_at: now or utcnow()}, synchronize_session=False)


def redeem(db, token: str, password: str, now: datetime.datetime | None = None) -> User | None:
    """Set ``password`` on the account ``token`` belongs to, or None if the link is no good.

    The link is claimed with one conditional update, so two requests racing on
    the same token cannot both succeed.
    """
    now = now or utcnow()
    reset = db.query(PasswordReset).filter(PasswordReset.token_hash == _digest(token)).first()
    if reset is None:
        return None
    user = db.get(User, reset.user_id)
    if user is None or not user.is_active:
        return None
    claimed = (
        db.query(PasswordReset)
        .filter(PasswordReset.id == reset.id, PasswordReset.used_at.is_(None), PasswordReset.expires_at > now)
        .update({PasswordReset.used_at: now}, synchronize_session=False)
    )
    if claimed != 1:
        return None
    user.password_hash = get_password_hash(password)
    user.token_version = (user.token_version or 0) + 1
    spend_all(db, user, now)
    db.commit()
    return user
