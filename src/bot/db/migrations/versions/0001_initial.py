from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'channels',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('tg_chat_id', sa.BigInteger(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('username', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('tg_chat_id', name='uq_channels_tg_chat_id'),
        schema='finance',
    )

    op.create_table(
        'categories',
        sa.Column('id', sa.SmallInteger(), primary_key=True, autoincrement=True),
        sa.Column('code', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.UniqueConstraint('code', name='uq_categories_code'),
        schema='finance',
    )

    op.create_table(
        'users',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('tg_user_id', sa.BigInteger(), nullable=False),
        sa.Column('first_name', sa.Text(), nullable=True),
        sa.Column('last_name', sa.Text(), nullable=True),
        sa.Column('username', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('tg_user_id', name='uq_users_tg_user_id'),
        schema='finance',
    )

    op.create_table(
        'operations',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('op_type', sa.SmallInteger(), nullable=False),
        sa.Column('category_id', sa.SmallInteger(), sa.ForeignKey('finance.categories.id'), nullable=False),
        sa.Column('amount_kop', sa.BigInteger(), nullable=False),
        sa.Column('currency', sa.CHAR(length=3), nullable=False, server_default=sa.text("'RUB'")),
        sa.Column('free_text_reason', sa.Text(), nullable=True),
        sa.Column('created_by_user_id', sa.BigInteger(), sa.ForeignKey('finance.users.id'), nullable=False),
        sa.Column('is_general', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('dedup_hash', sa.Text(), nullable=False),
        sa.UniqueConstraint('dedup_hash', name='uq_operations_dedup_hash'),
        schema='finance',
    )

    op.create_table(
        'operation_channels',
        sa.Column('operation_id', sa.BigInteger(), sa.ForeignKey('finance.operations.id'), primary_key=True, nullable=False),
        sa.Column('channel_id', sa.BigInteger(), sa.ForeignKey('finance.channels.id'), primary_key=True, nullable=False),
        schema='finance',
    )

    op.create_index('ix_channels_tg_chat_id', 'channels', ['tg_chat_id'], unique=True, schema='finance')


def downgrade() -> None:
    op.drop_index('ix_channels_tg_chat_id', table_name='channels', schema='finance')
    op.drop_table('operation_channels', schema='finance')
    op.drop_table('operations', schema='finance')
    op.drop_table('users', schema='finance')
    op.drop_table('categories', schema='finance')
    op.drop_table('channels', schema='finance')
