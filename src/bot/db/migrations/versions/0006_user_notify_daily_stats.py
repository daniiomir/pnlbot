from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0006_user_notify_daily_stats'
down_revision = '0005_channel_daily_churn'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('notify_daily_stats', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        schema='finance',
    )


def downgrade() -> None:
    op.drop_column('users', 'notify_daily_stats', schema='finance')


