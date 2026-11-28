# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import uuid

from app.models import AdminUser, User


def active_staff(db, user_id):
    return db.query(AdminUser).filter_by(user_id=user_id, is_active=True).one_or_none()


def confirmed_user(db, user_id, email):
    try:
        key = uuid.UUID(str(user_id))
    except (TypeError, ValueError):
        return None
    user = db.get(User, key)
    if user and user.email == email and user.is_active and not user.deletion_requested_at and not user.trashed_at:
        return user
    return None
