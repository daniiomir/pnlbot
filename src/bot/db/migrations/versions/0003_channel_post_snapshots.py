from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0003_channel_post_snapshots'
down_revision = '0002_operation_receipt_comment'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extend channels
    op.add_column('channels', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')), schema='finance')
    op.add_column('channels', sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True), schema='finance')
    op.add_column('channels', sa.Column('last_error', sa.Text(), nullable=True), schema='finance')
    op.add_column('channels', sa.Column('added_by_user_id', sa.BigInteger(), sa.ForeignKey('finance.users.id'), nullable=True), schema='finance')

    # Channel daily snapshots
    op.create_table(
        'channel_daily_snapshots',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('channel_id', sa.BigInteger(), sa.ForeignKey('finance.channels.id'), nullable=False),
        sa.Column('snapshot_date', sa.DateTime(timezone=False), nullable=False),
        sa.Column('subscribers_count', sa.BigInteger(), nullable=True),
        sa.Column('collected_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('channel_id', 'snapshot_date', name='uq_channel_daily'),
        schema='finance',
    )

    # Post snapshots per day
    op.create_table(
        'post_snapshots',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('channel_id', sa.BigInteger(), sa.ForeignKey('finance.channels.id'), nullable=False),
        sa.Column('message_id', sa.BigInteger(), nullable=False),
        sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('snapshot_date', sa.DateTime(timezone=False), nullable=False),
        sa.Column('views', sa.BigInteger(), nullable=True),
        sa.Column('forwards', sa.BigInteger(), nullable=True),
        sa.Column('reactions_total', sa.BigInteger(), nullable=True),
        sa.Column('collected_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('channel_id', 'message_id', 'snapshot_date', name='uq_post_daily'),
        schema='finance',
    )


def downgrade() -> None:
    op.drop_table('post_snapshots', schema='finance')
    op.drop_table('channel_daily_snapshots', schema='finance')
    op.drop_column('channels', 'added_by_user_id', schema='finance')
    op.drop_column('channels', 'last_error', schema='finance')
    op.drop_column('channels', 'last_success_at', schema='finance')
    op.drop_column('channels', 'is_active', schema='finance')


