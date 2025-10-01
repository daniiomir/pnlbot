from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0002_operation_receipt_comment'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('operations', sa.Column('receipt_url', sa.Text(), nullable=True), schema='finance')
    op.add_column('operations', sa.Column('comment', sa.Text(), nullable=True), schema='finance')


def downgrade() -> None:
    op.drop_column('operations', 'comment', schema='finance')
    op.drop_column('operations', 'receipt_url', schema='finance')


