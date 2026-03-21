"""initial tables for reports and push subscriptions

Revision ID: 001_initial
Revises:
Create Date: 2026-03-20 13:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("session_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=True, server_default=sa.text("0.0")),
        sa.Column("verdict", sa.Text(), nullable=True),
        sa.Column("output_formats", sa.Text(), nullable=True, server_default=sa.text("'[]'")),
    )

    op.create_table(
        "push_subscriptions",
        sa.Column("session_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("subscription_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("push_subscriptions")
    op.drop_table("reports")
