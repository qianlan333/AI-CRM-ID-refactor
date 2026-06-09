"""add wechat pay order unionid lookup index"""

from __future__ import annotations

from alembic import op


revision = "0029_wechat_pay_order_unionid_index"
down_revision = "0028_owner_migration_excel_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_orders_unionid_created
        ON wechat_pay_orders (unionid, created_at DESC, id DESC)
        WHERE unionid IS NOT NULL AND unionid <> ''
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_wechat_pay_orders_unionid_created")
