# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Fail when the migrations and the models disagree.

The test suite builds its schema with ``Base.metadata.create_all`` against
SQLite, so it never runs a migration at all. A model changed without a matching
migration passes the suite and breaks on deploy instead. This runs against a
real Postgres already migrated to head and reports whatever alembic would still
want to autogenerate, which is exactly the difference that would have broken.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

import app.models  # noqa: F401
from app.config import settings
from app.database import Base


def drift():
    engine = create_engine(settings.DATABASE_URL)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            return compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()


def main():
    difference = drift()
    if not difference:
        print("migrations match the models")
        return 0

    print("migrations and models disagree:\n")
    for entry in difference:
        print("  %s" % (entry,))
    print("\nGenerate the missing migration with:")
    print("  alembic revision --autogenerate -m '<what changed>'")
    return 1


if __name__ == "__main__":
    sys.exit(main())
