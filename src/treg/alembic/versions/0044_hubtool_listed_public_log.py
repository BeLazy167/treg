"""hubtool.listed + hubtool.public_log — the maker's two distribution switches (docs/hub-listing-decisions.md)

Revision ID: 0044
Revises: 0043
Create Date: 2026-09-16

Two boolean columns with server defaults: listed false (a hub tool stays off search until the
maker lists it), public_log true (the share page shows the recent-runs log unless switched off).
Metadata-only on Postgres.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044"
down_revision: str | Sequence[str] | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("hubtool", sa.Column("listed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("hubtool", sa.Column("public_log", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table("hubtool") as batch:
        batch.drop_column("public_log")
        batch.drop_column("listed")
