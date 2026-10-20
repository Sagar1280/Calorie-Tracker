"""food review history

Revision ID: b7f4c2a9d110
Revises: a027d87c2247
Create Date: 2026-10-20 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7f4c2a9d110"
down_revision: Union[str, Sequence[str], None] = "a027d87c2247"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "food_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "is_verified", sa.Boolean(), server_default="0", nullable=False
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('updated', 'approved', 'rejected')",
            name="ck_food_reviews_action",
        ),
        sa.CheckConstraint(
            "status IN ('approved', 'pending', 'rejected', 'private')",
            name="ck_food_reviews_status",
        ),
        sa.ForeignKeyConstraint(["food_id"], ["foods.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("food_reviews", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_food_reviews_food_id"), ["food_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_food_reviews_reviewer_user_id"),
            ["reviewer_user_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_food_reviews_food_created",
            ["food_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("food_reviews", schema=None) as batch_op:
        batch_op.drop_index("ix_food_reviews_food_created")
        batch_op.drop_index(batch_op.f("ix_food_reviews_reviewer_user_id"))
        batch_op.drop_index(batch_op.f("ix_food_reviews_food_id"))
    op.drop_table("food_reviews")
