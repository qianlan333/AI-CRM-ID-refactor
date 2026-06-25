"""add ai audience package sender whitelist.

Revision ID: 0051_ai_audience_sender_whitelist
Revises: 0049_group_ops_workspace_governance
"""

from __future__ import annotations

from alembic import op


revision = "0051_ai_audience_sender_whitelist"
down_revision = "0049_group_ops_workspace_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_audience_package_sender (
            id BIGSERIAL PRIMARY KEY,
            package_id BIGINT NOT NULL REFERENCES ai_audience_package(id) ON DELETE CASCADE,
            sender_userid TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            priority INT NOT NULL DEFAULT 100,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_ai_audience_package_sender UNIQUE (package_id, sender_userid),
            CONSTRAINT ck_ai_audience_package_sender_status CHECK (status IN ('active', 'paused'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_audience_package_sender_active
        ON ai_audience_package_sender(package_id, status, priority)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_ai_audience_package_sender_active")
    op.execute("DROP TABLE IF EXISTS ai_audience_package_sender")
