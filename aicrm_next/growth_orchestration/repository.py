from __future__ import annotations

import os
from typing import Protocol

from sqlalchemy import text

from aicrm_next.shared.db_session import get_session_factory

from .dto import GrowthMember, GrowthProgram


class GrowthProgramRepository(Protocol):
    def list_programs(self, *, limit: int = 50, offset: int = 0) -> list[GrowthProgram]: ...

    def list_members(self, *, limit: int = 50, offset: int = 0) -> list[GrowthMember]: ...


class EmptyGrowthProgramRepository:
    def list_programs(self, *, limit: int = 50, offset: int = 0) -> list[GrowthProgram]:
        return []

    def list_members(self, *, limit: int = 50, offset: int = 0) -> list[GrowthMember]:
        return []


class InMemoryGrowthProgramRepository(EmptyGrowthProgramRepository):
    def __init__(self, items: list[GrowthProgram], members: list[GrowthMember] | None = None) -> None:
        self._items = list(items)
        self._members = list(members or [])

    def list_programs(self, *, limit: int = 50, offset: int = 0) -> list[GrowthProgram]:
        return self._items[offset : offset + limit]

    def list_members(self, *, limit: int = 50, offset: int = 0) -> list[GrowthMember]:
        return self._members[offset : offset + limit]


class PostgresGrowthProgramRepository:
    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory or get_session_factory()

    def list_programs(self, *, limit: int = 50, offset: int = 0) -> list[GrowthProgram]:
        with self._session_factory() as session:
            rows = session.execute(text(GROWTH_PROGRAMS_SQL), {"limit": int(limit), "offset": int(offset)}).mappings().all()
        return [GrowthProgram(**dict(row)) for row in rows]

    def list_members(self, *, limit: int = 50, offset: int = 0) -> list[GrowthMember]:
        with self._session_factory() as session:
            rows = session.execute(text(GROWTH_MEMBERS_SQL), {"limit": int(limit), "offset": int(offset)}).mappings().all()
        return [GrowthMember(**dict(row)) for row in rows]


def build_growth_program_repository() -> GrowthProgramRepository:
    if not str(os.getenv("DATABASE_URL") or "").strip():
        return EmptyGrowthProgramRepository()
    return PostgresGrowthProgramRepository()


GROWTH_PROGRAMS_SQL = """
WITH campaign_counts AS (
    SELECT
        campaign_id,
        COUNT(*)::int AS member_count,
        COUNT(*) FILTER (WHERE status NOT IN ('cancelled', 'failed', 'finished', 'stopped'))::int AS active_member_count,
        MAX(updated_at) AS last_member_activity_at
    FROM campaign_members
    GROUP BY campaign_id
),
campaign_task_counts AS (
    SELECT campaign_id, COUNT(*)::int AS task_count, MAX(updated_at) AS last_task_activity_at
    FROM campaign_steps
    GROUP BY campaign_id
),
group_counts AS (
    SELECT
        plan_id,
        COALESCE(SUM(internal_member_count_snapshot + external_member_count_snapshot), 0)::int AS member_count,
        COALESCE(SUM(internal_member_count_snapshot + external_member_count_snapshot) FILTER (WHERE status = 'active'), 0)::int AS active_member_count,
        MAX(COALESCE(removed_at, created_at)) AS last_member_activity_at
    FROM automation_group_ops_plan_groups
    GROUP BY plan_id
),
group_task_counts AS (
    SELECT plan_id, COUNT(*)::int AS task_count, MAX(updated_at) AS last_task_activity_at
    FROM automation_group_ops_plan_nodes
    GROUP BY plan_id
),
cloud_counts AS (
    SELECT
        plan_id,
        COUNT(*)::int AS member_count,
        COUNT(*) FILTER (WHERE send_status NOT IN ('failed', 'cancelled'))::int AS active_member_count,
        COALESCE(SUM(planned_message_count), 0)::int AS task_count,
        MAX(updated_at) AS last_activity_at
    FROM cloud_broadcast_plan_recipients
    GROUP BY plan_id
),
ai_audience_counts AS (
    SELECT
        package_id,
        COUNT(*)::int AS member_count,
        COUNT(*) FILTER (WHERE status = 'active')::int AS active_member_count,
        MAX(last_updated_at) AS last_member_activity_at
    FROM ai_audience_member_current
    GROUP BY package_id
),
programs AS (
    SELECT
        'campaign:' || c.campaign_code AS program_key,
        'campaign' AS program_type,
        COALESCE(c.display_name, '') AS title,
        COALESCE(NULLIF(c.run_status, ''), c.review_status, '') AS status,
        COALESCE(c.owner_userid, '') AS owner_userid,
        COALESCE(cc.member_count, 0)::int AS member_count,
        COALESCE(cc.active_member_count, 0)::int AS active_member_count,
        COALESCE(ct.task_count, 0)::int AS task_count,
        GREATEST(
            c.updated_at,
            COALESCE(cc.last_member_activity_at, c.updated_at),
            COALESCE(ct.last_task_activity_at, c.updated_at)
        ) AS last_activity_at,
        'campaigns' AS source_table,
        c.id::text AS source_id
    FROM campaigns c
    LEFT JOIN campaign_counts cc ON cc.campaign_id = c.id
    LEFT JOIN campaign_task_counts ct ON ct.campaign_id = c.id
    UNION ALL
    SELECT
        'group_ops:' || COALESCE(NULLIF(p.plan_code, ''), p.id::text) AS program_key,
        'group_ops' AS program_type,
        COALESCE(p.plan_name, '') AS title,
        COALESCE(p.status, '') AS status,
        COALESCE(p.owner_userid, '') AS owner_userid,
        COALESCE(gc.member_count, 0)::int AS member_count,
        COALESCE(gc.active_member_count, 0)::int AS active_member_count,
        COALESCE(gt.task_count, 0)::int AS task_count,
        GREATEST(
            p.updated_at,
            COALESCE(gc.last_member_activity_at, p.updated_at),
            COALESCE(gt.last_task_activity_at, p.updated_at)
        ) AS last_activity_at,
        'automation_group_ops_plans' AS source_table,
        p.id::text AS source_id
    FROM automation_group_ops_plans p
    LEFT JOIN group_counts gc ON gc.plan_id = p.id
    LEFT JOIN group_task_counts gt ON gt.plan_id = p.id
    WHERE p.archived_at IS NULL
    UNION ALL
    SELECT
        'cloud_plan:' || p.plan_id AS program_key,
        'cloud_plan' AS program_type,
        COALESCE(NULLIF(p.intent, ''), p.plan_id) AS title,
        COALESCE(p.status, '') AS status,
        COALESCE(p.operator, '') AS owner_userid,
        COALESCE(cc.member_count, 0)::int AS member_count,
        COALESCE(cc.active_member_count, 0)::int AS active_member_count,
        COALESCE(cc.task_count, 0)::int AS task_count,
        GREATEST(
            p.updated_at,
            COALESCE(cc.last_activity_at, p.updated_at)
        ) AS last_activity_at,
        'cloud_broadcast_plans' AS source_table,
        p.plan_id AS source_id
    FROM cloud_broadcast_plans p
    LEFT JOIN cloud_counts cc ON cc.plan_id = p.plan_id
    UNION ALL
    SELECT
        'ai_audience_package:' || p.package_key AS program_key,
        'ai_audience_package' AS program_type,
        COALESCE(p.name, '') AS title,
        COALESCE(p.status, '') AS status,
        '' AS owner_userid,
        COALESCE(aac.member_count, 0)::int AS member_count,
        COALESCE(aac.active_member_count, 0)::int AS active_member_count,
        0 AS task_count,
        GREATEST(p.updated_at, COALESCE(aac.last_member_activity_at, p.updated_at)) AS last_activity_at,
        'ai_audience_package' AS source_table,
        p.id::text AS source_id
    FROM ai_audience_package p
    LEFT JOIN ai_audience_counts aac ON aac.package_id = p.id
)
SELECT *
FROM programs
ORDER BY last_activity_at DESC NULLS LAST, program_key ASC
LIMIT :limit OFFSET :offset
"""


GROWTH_MEMBERS_SQL = """
WITH members AS (
    SELECT
        'campaign:' || c.campaign_code AS program_key,
        cm.unionid AS unionid,
        'step:' || cm.current_step_index::text AS current_stage,
        COALESCE(cm.status, '') AS status,
        COALESCE(c.owner_userid, '') AS owner_userid,
        COALESCE(cm.last_step_sent_at, cm.updated_at, cm.created_at) AS last_touch_at,
        cm.next_due_at AS next_task_at,
        'campaign_members' AS source_table,
        cm.id::text AS source_id
    FROM campaign_members cm
    JOIN campaigns c ON c.id = cm.campaign_id
    WHERE COALESCE(cm.unionid, '') <> ''
    UNION ALL
    SELECT
        'cloud_plan:' || r.plan_id AS program_key,
        r.unionid AS unionid,
        COALESCE(r.approval_status, '') AS current_stage,
        COALESCE(r.send_status, '') AS status,
        COALESCE(r.owner_userid, '') AS owner_userid,
        COALESCE(r.updated_at, r.created_at) AS last_touch_at,
        NULL::timestamptz AS next_task_at,
        'cloud_broadcast_plan_recipients' AS source_table,
        r.id::text AS source_id
    FROM cloud_broadcast_plan_recipients r
    WHERE COALESCE(r.unionid, '') <> ''
    UNION ALL
    SELECT
        'ai_audience_package:' || p.package_key AS program_key,
        m.unionid AS unionid,
        COALESCE(m.event_source_key, '') AS current_stage,
        COALESCE(m.status, '') AS status,
        COALESCE(m.owner_userid, '') AS owner_userid,
        COALESCE(m.last_seen_at, m.last_updated_at, m.updated_at, m.created_at) AS last_touch_at,
        NULL::timestamptz AS next_task_at,
        'ai_audience_member_current' AS source_table,
        m.id::text AS source_id
    FROM ai_audience_member_current m
    JOIN ai_audience_package p ON p.id = m.package_id
    WHERE COALESCE(m.unionid, '') <> ''
)
SELECT *
FROM members
ORDER BY last_touch_at DESC NULLS LAST, program_key ASC, unionid ASC
LIMIT :limit OFFSET :offset
"""
