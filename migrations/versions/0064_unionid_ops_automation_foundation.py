"""add unionid foundation columns for ops and automation tables.

Revision ID: 0064_unionid_ops_automation_foundation
Revises: 0063_unionid_business_table_foundation
"""

from __future__ import annotations

from alembic import op


revision = "0064_unionid_ops_automation_foundation"
down_revision = "0063_unionid_business_table_foundation"
branch_labels = None
depends_on = None


UNIONID_TABLES = [
    "contact_tags",
    "archived_messages",
    "class_user_status_current",
    "class_user_status_history",
    "user_ops_pool_current_next",
    "user_ops_do_not_disturb_next",
    "automation_channel_contact",
    "automation_channel_assignment_event",
    "automation_event_v2",
    "automation_membership_v2",
    "automation_task_plan_v2",
    "ai_audience_member_current",
    "ai_audience_member_event",
]

TARGET_UNIONIDS_TABLES = [
    "user_ops_send_records_next",
    "broadcast_jobs",
    "external_effect_job",
]


def upgrade() -> None:
    for table_name in UNIONID_TABLES:
        op.execute(f"ALTER TABLE IF EXISTS {table_name} ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''")
        op.execute(
            f"""
            CREATE INDEX IF NOT EXISTS ix_{table_name}_unionid
            ON {table_name} (unionid)
            WHERE unionid <> ''
            """
        )

    for table_name in TARGET_UNIONIDS_TABLES:
        op.execute(f"ALTER TABLE IF EXISTS {table_name} ADD COLUMN IF NOT EXISTS target_unionids_json JSONB NOT NULL DEFAULT '[]'::jsonb")
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table_name}_target_unionids_json ON {table_name} USING GIN (target_unionids_json)")

    op.execute("ALTER TABLE IF EXISTS external_effect_job ADD COLUMN IF NOT EXISTS target_unionid TEXT NOT NULL DEFAULT ''")
    op.execute("CREATE INDEX IF NOT EXISTS ix_external_effect_job_target_unionid ON external_effect_job (target_unionid) WHERE target_unionid <> ''")

    _backfill_single_unionid_tables()
    _backfill_target_unionids()
    _drop_legacy_channel_identity_columns()
    _drop_legacy_ai_audience_identity_columns()


def _backfill_single_unionid_tables() -> None:
    for table_name in [
        "contact_tags",
        "archived_messages",
        "class_user_status_current",
        "class_user_status_history",
        "user_ops_pool_current_next",
        "user_ops_do_not_disturb_next",
        "automation_channel_contact",
        "automation_event_v2",
        "automation_membership_v2",
        "ai_audience_member_current",
        "ai_audience_member_event",
    ]:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF to_regclass('public.{table_name}') IS NOT NULL
                   AND EXISTS (
                       SELECT 1 FROM information_schema.columns
                       WHERE table_schema = 'public' AND table_name = '{table_name}' AND column_name = 'external_userid'
                   ) THEN
                    UPDATE {table_name} target
                    SET unionid = cui.unionid
                    FROM crm_user_identity cui
                    WHERE COALESCE(target.unionid, '') = ''
                      AND COALESCE(target.external_userid, '') <> ''
                      AND (
                          cui.primary_external_userid = target.external_userid
                          OR jsonb_exists(cui.external_userids_json, target.external_userid)
                      );
                END IF;
            END $$;
            """
        )

    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.automation_channel_contact') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'automation_channel_contact' AND column_name = 'external_contact_id'
               ) THEN
                UPDATE automation_channel_contact target
                SET unionid = cui.unionid
                FROM crm_user_identity cui
                WHERE COALESCE(target.unionid, '') = ''
                  AND COALESCE(target.external_contact_id, '') <> ''
                  AND (
                      cui.primary_external_userid = target.external_contact_id
                      OR jsonb_exists(cui.external_userids_json, target.external_contact_id)
                  );
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.automation_channel_assignment_event') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'automation_channel_assignment_event' AND column_name = 'external_contact_id'
               ) THEN
                UPDATE automation_channel_assignment_event target
                SET unionid = cui.unionid
                FROM crm_user_identity cui
                WHERE COALESCE(target.unionid, '') = ''
                  AND COALESCE(target.external_contact_id, '') <> ''
                  AND (
                      cui.primary_external_userid = target.external_contact_id
                      OR jsonb_exists(cui.external_userids_json, target.external_contact_id)
                  );
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        UPDATE ai_audience_member_current
        SET unionid = identity_value
        WHERE COALESCE(unionid, '') = ''
          AND identity_type = 'unionid'
          AND COALESCE(identity_value, '') <> ''
        """
    )
    op.execute(
        """
        UPDATE ai_audience_member_event
        SET unionid = identity_value
        WHERE COALESCE(unionid, '') = ''
          AND identity_type = 'unionid'
          AND COALESCE(identity_value, '') <> ''
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.automation_task_plan_v2') IS NOT NULL
               AND to_regclass('public.automation_membership_v2') IS NOT NULL THEN
                UPDATE automation_task_plan_v2 plan
                SET unionid = membership.unionid
                FROM automation_membership_v2 membership
                WHERE plan.membership_id = membership.id
                  AND COALESCE(plan.unionid, '') = ''
                  AND COALESCE(membership.unionid, '') <> '';
            END IF;
        END $$;
        """
    )


def _backfill_target_unionids() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.broadcast_jobs') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'broadcast_jobs' AND column_name = 'target_external_userids'
               ) THEN
                UPDATE broadcast_jobs job
                SET target_unionids_json = COALESCE(resolved.unionids, '[]'::jsonb)
                FROM (
                    SELECT job_inner.id,
                           COALESCE(jsonb_agg(DISTINCT cui.unionid) FILTER (WHERE cui.unionid IS NOT NULL), '[]'::jsonb) AS unionids
                    FROM broadcast_jobs job_inner
                    CROSS JOIN LATERAL jsonb_array_elements_text(job_inner.target_external_userids) AS external_ids(external_userid)
                    JOIN crm_user_identity cui
                      ON cui.primary_external_userid = external_ids.external_userid
                      OR jsonb_exists(cui.external_userids_json, external_ids.external_userid)
                    GROUP BY job_inner.id
                ) resolved
                WHERE job.id = resolved.id
                  AND jsonb_array_length(job.target_unionids_json) = 0;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.external_effect_job') IS NOT NULL THEN
                UPDATE external_effect_job job
                SET target_unionid = cui.unionid,
                    target_unionids_json = jsonb_build_array(cui.unionid)
                FROM crm_user_identity cui
                WHERE COALESCE(job.target_unionid, '') = ''
                  AND COALESCE(job.target_id, '') <> ''
                  AND (
                      cui.primary_external_userid = job.target_id
                      OR jsonb_exists(cui.external_userids_json, job.target_id)
                      OR cui.unionid = job.target_id
                  );
            END IF;
        END $$;
        """
    )


def _drop_legacy_ai_audience_identity_columns() -> None:
    for table_name in ["ai_audience_member_event", "ai_audience_member_current"]:
        op.execute(f"ALTER TABLE IF EXISTS {table_name} DROP COLUMN IF EXISTS person_id")
        op.execute(f"ALTER TABLE IF EXISTS {table_name} DROP COLUMN IF EXISTS external_userid")


def _drop_legacy_channel_identity_columns() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_channel_contact_channel_unionid
        ON automation_channel_contact (channel_id, unionid)
        WHERE unionid <> ''
        """
    )
    op.execute("ALTER TABLE IF EXISTS automation_channel_contact DROP COLUMN IF EXISTS external_contact_id")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_automation_channel_contact_channel_unionid")
    op.execute("ALTER TABLE IF EXISTS automation_channel_contact ADD COLUMN IF NOT EXISTS external_contact_id TEXT NOT NULL DEFAULT ''")
    op.execute("DROP INDEX IF EXISTS ix_external_effect_job_target_unionid")
    op.execute("ALTER TABLE IF EXISTS external_effect_job DROP COLUMN IF EXISTS target_unionid")
    for table_name in TARGET_UNIONIDS_TABLES:
        op.execute(f"DROP INDEX IF EXISTS ix_{table_name}_target_unionids_json")
        op.execute(f"ALTER TABLE IF EXISTS {table_name} DROP COLUMN IF EXISTS target_unionids_json")
    for table_name in reversed(UNIONID_TABLES):
        op.execute(f"DROP INDEX IF EXISTS ix_{table_name}_unionid")
        op.execute(f"ALTER TABLE IF EXISTS {table_name} DROP COLUMN IF EXISTS unionid")
