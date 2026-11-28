# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import sys

from app.admin import roles
from app.admin.identity import confirmed_user
from app.database import SessionLocal
from app.models import AdminUser


def main(argv):
    if len(argv) not in (2, 3):
        sys.exit("usage: python -m app.admin.bootstrap <email> <confirmed-user-id> [role]")
    email, user_id = argv[0].strip().lower(), argv[1]
    role = argv[2] if len(argv) == 3 else None
    if role is not None and not roles.is_valid(role):
        sys.exit("role must be one of: %s" % ", ".join(roles.ROLES))

    with SessionLocal() as db:
        user = confirmed_user(db, user_id, email)
        if user is None:
            sys.exit("No active dashboard account matches that ID and email.")
        admin = db.query(AdminUser).filter_by(email=email).with_for_update().one_or_none()
        if admin is None:
            if role is None:
                sys.exit("Choose a role for the new staff member.")
            admin = AdminUser(email=email, role=role)
            db.add(admin)
        elif admin.user_id not in (None, user.id):
            sys.exit("This staff record already belongs to another dashboard account.")
        if role is not None:
            admin.role = role
            admin.is_active = True
        admin.user_id = user.id
        db.commit()
        print(f"Linked {email} as {admin.role}.")


if __name__ == "__main__":
    main(sys.argv[1:])
