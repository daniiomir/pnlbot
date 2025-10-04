from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0007_cats_income_expense'
down_revision = '0006_user_notify_daily_stats'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Rename existing generic ad_revenue to direct revenue name
    conn.execute(sa.text(
        """
        UPDATE finance.categories
        SET name = 'Выручка с прямой рекламы'
        WHERE code = 'ad_revenue'
        """
    ))

    # Insert other new categories (excluding the duplicate direct revenue code)
    conn.execute(sa.text(
        """
        INSERT INTO finance.categories (code, name, is_active)
        VALUES
            ('ad_revenue_rsy', 'Выручка с РСЯ', true),
            ('ad_revenue_bk', 'Выручка с БК', true),
            ('services_costs', 'Затраты на сервисы', true),
            ('it_infra_costs', 'Затраты на IT инфру', true)
        ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, is_active = EXCLUDED.is_active
        """
    ))

    # If duplicate code was previously inserted, clean it up safely
    conn.execute(sa.text(
        """
        DELETE FROM finance.categories WHERE code = 'ad_revenue_direct'
        """
    ))


def downgrade() -> None:
    conn = op.get_bind()
    # Recreate deleted duplicate code just in case; then revert rename
    conn.execute(sa.text(
        """
        INSERT INTO finance.categories (code, name, is_active)
        VALUES ('ad_revenue_direct', 'Выручка с прямой рекламой', true)
        ON CONFLICT (code) DO NOTHING
        """
    ))
    conn.execute(sa.text(
        """
        UPDATE finance.categories
        SET name = 'Доход с рекламы'
        WHERE code = 'ad_revenue'
        """
    ))
    conn.execute(sa.text(
        """
        DELETE FROM finance.categories WHERE code IN (
            'ad_revenue_rsy', 'ad_revenue_bk', 'services_costs', 'it_infra_costs'
        )
        """
    ))


