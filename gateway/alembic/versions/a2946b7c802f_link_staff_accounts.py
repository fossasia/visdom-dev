# Copyright 2017-present, The Visdom Authors
"""Link staff to dashboard identities."""

import secrets

import bcrypt
import sqlalchemy as sa

from alembic import op

revision = "a2946b7c802f"
down_revision = "b7f2e4a9c613"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("admin_users") as table:
        table.add_column(sa.Column("user_id", sa.UUID(), nullable=True))
        table.create_foreign_key("fk_admin_user_identity", "users", ["user_id"], ["id"], ondelete="SET NULL")
        table.create_unique_constraint("uq_admin_user_identity", ["user_id"])
        table.drop_column("password_hash")


def downgrade():
    unusable = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt()).decode()
    with op.batch_alter_table("admin_users") as table:
        table.drop_constraint("uq_admin_user_identity", type_="unique")
        table.drop_constraint("fk_admin_user_identity", type_="foreignkey")
        table.drop_column("user_id")
        table.add_column(sa.Column("password_hash", sa.String(), nullable=False, server_default=unusable))
    with op.batch_alter_table("admin_users") as table:
        table.alter_column("password_hash", server_default=None)
