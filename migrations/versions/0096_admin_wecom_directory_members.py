"""add admin wecom directory members cache.

Revision ID: 0096_admin_wecom_directory_members
Revises: 0095_service_period_products
"""

from __future__ import annotations

from alembic import op


revision = "0096_admin_wecom_directory_members"
down_revision = "0095_service_period_products"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_wecom_directory_members (
            id BIGSERIAL PRIMARY KEY,
            corp_id TEXT NOT NULL DEFAULT '',
            wecom_userid TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            department_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            department_name TEXT NOT NULL DEFAULT '',
            position TEXT NOT NULL DEFAULT '',
            mobile TEXT NOT NULL DEFAULT '',
            avatar_url TEXT NOT NULL DEFAULT '',
            wecom_status TEXT NOT NULL DEFAULT '',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_synced_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT NOT NULL DEFAULT ''
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_admin_wecom_directory_members_corp_userid
        ON admin_wecom_directory_members (corp_id, wecom_userid)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_admin_wecom_directory_members_active
        ON admin_wecom_directory_members (corp_id, is_active, display_name)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_admin_wecom_directory_members_synced
        ON admin_wecom_directory_members (last_synced_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_admin_wecom_directory_members_synced")
    op.execute("DROP INDEX IF EXISTS ix_admin_wecom_directory_members_active")
    op.execute("DROP INDEX IF EXISTS ux_admin_wecom_directory_members_corp_userid")
    op.execute("DROP TABLE IF EXISTS admin_wecom_directory_members")
