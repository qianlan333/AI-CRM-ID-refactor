"""add commerce payment/refund fulfillment invariants.

Revision ID: 0101_commerce_fulfillment_invariants
Revises: 0100_external_effect_delivery_lease
"""

from __future__ import annotations

from alembic import op


revision = "0101_commerce_fulfillment_invariants"
down_revision = "0100_external_effect_delivery_lease"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_wechat_pay_refunds_out_refund_no
        ON wechat_pay_refunds (out_refund_no)
        WHERE out_refund_no <> ''
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_wechat_pay_refunds_refund_id
        ON wechat_pay_refunds (refund_id)
        WHERE refund_id <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_refunds_order_active
        ON wechat_pay_refunds (order_id, created_at DESC, id DESC)
        WHERE LOWER(COALESCE(status, '')) NOT IN ('failed', 'closed', 'abnormal', 'success')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_wechat_pay_refunds_order_active")
    op.execute("DROP INDEX IF EXISTS uq_wechat_pay_refunds_refund_id")
    op.execute("DROP INDEX IF EXISTS uq_wechat_pay_refunds_out_refund_no")
