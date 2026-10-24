"""photo meal analysis jobs

Revision ID: c9a1e5f7b220
Revises: b7f4c2a9d110
Create Date: 2026-10-20 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9a1e5f7b220"
down_revision: Union[str, Sequence[str], None] = "b7f4c2a9d110"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "photo_meal_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("meal", sa.String(length=16), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="pending", nullable=False
        ),
        sa.Column("image_path", sa.String(length=512), nullable=True),
        sa.Column("items", sa.JSON(), nullable=True),
        sa.Column("entry_ids", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_photo_meal_jobs_status",
        ),
        sa.CheckConstraint(
            "meal IN ('breakfast', 'lunch', 'dinner', 'snack')",
            name="ck_photo_meal_jobs_meal",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("photo_meal_jobs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_photo_meal_jobs_user_id"), ["user_id"], unique=False
        )
        batch_op.create_index(
            "ix_photo_meal_jobs_user_created",
            ["user_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("photo_meal_jobs", schema=None) as batch_op:
        batch_op.drop_index("ix_photo_meal_jobs_user_created")
        batch_op.drop_index(batch_op.f("ix_photo_meal_jobs_user_id"))
    op.drop_table("photo_meal_jobs")
