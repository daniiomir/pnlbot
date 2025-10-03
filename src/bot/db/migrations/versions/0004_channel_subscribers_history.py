from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0004_channel_subscribers_history'
down_revision = '0003_channel_post_snapshots'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'channel_subscribers_history',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('channel_id', sa.BigInteger(), sa.ForeignKey('finance.channels.id'), nullable=False),
        sa.Column('collected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('subscribers_count', sa.BigInteger(), nullable=True),
        schema='finance',
    )
    op.create_index(
        'ix_csh_channel_collected',
        'channel_subscribers_history',
        ['channel_id', 'collected_at'],
        unique=False,
        schema='finance',
    )


def downgrade() -> None:
    op.drop_index('ix_csh_channel_collected', table_name='channel_subscribers_history', schema='finance')
    op.drop_table('channel_subscribers_history', schema='finance')


