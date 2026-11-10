# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Holding an account to no plan limit at all, for a while.

A promotion, a pilot, or a customer who needs room today should not need a new
plan or a deploy. Staff switch the bypass on in the admin console, for one
account or for every account, and from the next request nothing the plan would
have refused is refused: no ceiling on workspaces, members, API keys or
storage, and nothing removed for being older than the plan keeps.

The account's plan is left exactly as it was, so switching the bypass off puts
back what was there before. Whatever was made in the meantime stays. The
account is only stopped from making more, the same as after a move to a smaller
plan.

The switch for everyone removes the storage ceilings too, and those are the
only thing between one busy account and a full disk. It is meant to be on for
days, with someone watching, and not left on.
"""

from sqlalchemy.orm import Session

from app.models import PlatformSwitch, User, utcnow

EVERYONE = "bypass_limits"


def for_everyone(db: Session) -> bool:
    """Whether every account's limits are bypassed right now.

    Read as a column rather than a row, so a session that loaded the switch
    earlier still sees a change made since.
    """
    return bool(
        db.query(PlatformSwitch.is_on).filter(PlatformSwitch.name == EVERYONE).scalar()
    )


def applies_to(db: Session, user: User | None) -> bool:
    """Whether this account is held to no limits, by its own switch or everyone's."""
    if user is not None and user.bypass_limits:
        return True
    return for_everyone(db)


def standing(db: Session) -> PlatformSwitch | None:
    """The switch for everyone as it was last left, or None if never touched."""
    return db.get(PlatformSwitch, EVERYONE)


def set_for_everyone(db: Session, on: bool, by: str | None = None) -> bool:
    """Turn the bypass for every account on or off. Returns whether it changed."""
    switch = db.get(PlatformSwitch, EVERYONE)
    if switch is None:
        switch = PlatformSwitch(name=EVERYONE, is_on=False)
        db.add(switch)
    if bool(switch.is_on) == bool(on):
        db.commit()
        return False
    switch.is_on = bool(on)
    switch.changed_at = utcnow()
    switch.changed_by = by
    db.commit()
    return True


def set_for_account(db: Session, user: User, on: bool) -> bool:
    """Turn one account's own bypass on or off. Returns whether it changed."""
    if bool(user.bypass_limits) == bool(on):
        return False
    user.bypass_limits = bool(on)
    db.commit()
    return True


def accounts(db: Session) -> list[User]:
    """The accounts with a bypass of their own, whatever the switch for everyone says."""
    return db.query(User).filter(User.bypass_limits.is_(True)).order_by(User.email).all()
