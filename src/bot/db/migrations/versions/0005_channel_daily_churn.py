from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0005_channel_daily_churn'
down_revision = '0004_channel_subscribers_history'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'channel_daily_churn',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('channel_id', sa.BigInteger(), sa.ForeignKey('finance.channels.id'), nullable=False),
        sa.Column('snapshot_date', sa.DateTime(timezone=False), nullable=False),
        sa.Column('joins_count', sa.BigInteger(), nullable=True),
        sa.Column('leaves_count', sa.BigInteger(), nullable=True),
        sa.Column('collected_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('channel_id', 'snapshot_date', name='uq_channel_daily_churn'),
        schema='finance',
    )


def downgrade() -> None:
    op.drop_table('channel_daily_churn', schema='finance')


