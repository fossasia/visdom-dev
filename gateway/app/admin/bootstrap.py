# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Creates or updates a staff account.

    python -m app.admin.bootstrap someone@fossasia.org superadmin
"""

import getpass
import sys

from app.admin import roles
from app.database import SessionLocal
from app.models import AdminUser
from app.security import get_password_hash


def main(argv):
    if len(argv) != 2:
        sys.exit("usage: python -m app.admin.bootstrap <email> <%s>" % "|".join(roles.ROLES))
    email, role = argv[0].strip().lower(), argv[1].strip()
    if not roles.is_valid(role):
        sys.exit("role must be one of: %s" % ", ".join(roles.ROLES))

    password = getpass.getpass("password: ")
    if len(password) < 12:
        sys.exit("password must be at least 12 characters")
    if password != getpass.getpass("confirm: "):
        sys.exit("passwords did not match")

    db = SessionLocal()
    try:
        admin = db.query(AdminUser).filter(AdminUser.email == email).first()
        if admin is None:
            admin = AdminUser(email=email, role=role, password_hash=get_password_hash(password))
            db.add(admin)
            action = "created"
        else:
            admin.role = role
            admin.password_hash = get_password_hash(password)
            admin.is_active = True
            action = "updated"
        db.commit()
        print("%s %s as %s" % (action, email, role))
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1:])
