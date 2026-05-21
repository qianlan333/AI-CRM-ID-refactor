#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
from psycopg.types.json import Jsonb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}
REQUIRED_DATABASE = "aicrm_old_flask_test"

SAMPLE = {
    "external_userid": "external_user_masked_automation_001",
    "customer_name": "customer_masked_automation_001",
    "mobile": "mobile_masked_automation_001",
    "owner_userid": "owner_masked_automation_001",
    "member_external_id": "automation_member_masked_001",
    "current_pool": "active_focus",
    "current_audience_code": "operating",
    "follow_type": "focus",
    "event_action": "automation_event_masked_001",
    "execution_id": "automation_execution_masked_001",
    "workflow_code": "automation_workflow_masked_001",
    "node_code": "automation_node_masked_001",
}


@dataclass(frozen=True)
class SafeDatabaseUrl:
    raw_url: str
    redacted_url: str
    host: str
    database_name: str


def redact_database_url(url: str) -> str:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    netloc = host
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    if parsed.username:
        netloc = f"{quote(parsed.username)}:***@{netloc}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def validate_database_url(url: str) -> SafeDatabaseUrl:
    if not url:
        raise ValueError("database URL is required")
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    database_name = parsed.path.lstrip("/")
    if parsed.scheme not in {"postgresql", "postgresql+psycopg", "postgres"}:
        raise ValueError(f"unsupported database URL scheme: {parsed.scheme}")
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"refusing non-local database host: {host}")
    if database_name != REQUIRED_DATABASE:
        raise ValueError(f"refusing database {database_name!r}; expected {REQUIRED_DATABASE!r}")
    if "test" not in database_name:
        raise ValueError(f"refusing database without test marker: {database_name}")
    return SafeDatabaseUrl(
        raw_url=url,
        redacted_url=redact_database_url(url),
        host=host,
        database_name=database_name,
    )


def _now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def seed_sample(database_url: str, *, apply: bool) -> dict[str, object]:
    safe_url = validate_database_url(database_url)
    plan = {
        "database": safe_url.database_name,
        "host": safe_url.host,
        "redacted_url": safe_url.redacted_url,
        "apply": apply,
        "sample": {
            "external_userid": SAMPLE["external_userid"],
            "customer_name": SAMPLE["customer_name"],
            "mobile": SAMPLE["mobile"],
            "owner_userid": SAMPLE["owner_userid"],
            "member_external_id": SAMPLE["member_external_id"],
            "current_pool": SAMPLE["current_pool"],
            "current_audience_code": SAMPLE["current_audience_code"],
            "follow_type": SAMPLE["follow_type"],
            "execution_id": SAMPLE["execution_id"],
        },
        "tables": [
            "automation_program",
            "automation_member",
            "automation_member_audience_entry",
            "automation_event",
            "automation_workflow",
            "automation_workflow_node",
            "automation_workflow_execution",
            "automation_workflow_execution_item",
        ],
    }
    if not apply:
        return {"ok": True, "dry_run": True, **plan}

    now = _now_text()
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO automation_program (program_code, program_name, description, status, config_json, created_by, updated_by)
                VALUES ('signup_conversion_v1', '默认自动化转化方案', 'masked automation local test program', 'active', %s, 'aicrm_next_seed', 'aicrm_next_seed')
                ON CONFLICT (program_code) DO UPDATE SET
                    program_name = EXCLUDED.program_name,
                    description = EXCLUDED.description,
                    status = 'active',
                    updated_by = EXCLUDED.updated_by,
                    updated_at = NOW()
                RETURNING id
                """,
                (Jsonb({"source": "aicrm_next_local_masked_automation_sample"}),),
            )
            program_id = int(cur.fetchone()[0])

            cur.execute(
                "SELECT id FROM automation_member WHERE external_contact_id = %s",
                (SAMPLE["external_userid"],),
            )
            old_member = cur.fetchone()
            if old_member:
                old_member_id = int(old_member[0])
                cur.execute("DELETE FROM automation_workflow_execution_item WHERE member_id = %s", (old_member_id,))
                cur.execute("DELETE FROM automation_member_audience_entry WHERE member_id = %s", (old_member_id,))
                cur.execute("DELETE FROM automation_event WHERE member_id = %s", (old_member_id,))
                cur.execute("DELETE FROM automation_member WHERE id = %s", (old_member_id,))
            cur.execute(
                "DELETE FROM automation_workflow_execution WHERE execution_id = %s",
                (SAMPLE["execution_id"],),
            )

            cur.execute(
                """
                INSERT INTO automation_member (
                    external_contact_id, phone, owner_staff_id, in_pool, current_pool, follow_type,
                    questionnaire_status, decision_source, source_type, current_audience_code,
                    current_audience_entered_at, profile_segment_key, behavior_tier_key,
                    last_active_pool, joined_at, created_at, updated_at
                )
                VALUES (%s, %s, %s, TRUE, %s, %s, 'submitted', 'seed', 'local_test', %s, %s, 'profile_masked_001',
                        'behavior_masked_001', %s, %s, NOW(), NOW())
                RETURNING id
                """,
                (
                    SAMPLE["external_userid"],
                    SAMPLE["mobile"],
                    SAMPLE["owner_userid"],
                    SAMPLE["current_pool"],
                    SAMPLE["follow_type"],
                    SAMPLE["current_audience_code"],
                    now,
                    SAMPLE["current_pool"],
                    now,
                ),
            )
            member_id = int(cur.fetchone()[0])

            cur.execute(
                """
                INSERT INTO automation_member_audience_entry (
                    member_id, audience_code, entered_at, is_current, entry_source, entry_reason, source_snapshot_json
                )
                VALUES (%s, %s, %s, TRUE, 'aicrm_next_seed', 'masked_local_automation_sample', %s)
                """,
                (
                    member_id,
                    SAMPLE["current_audience_code"],
                    now,
                    Jsonb({"external_userid": SAMPLE["external_userid"], "masked": True}),
                ),
            )
            cur.execute(
                """
                INSERT INTO automation_event (
                    member_id, action, operator_type, operator_id, before_snapshot, after_snapshot, remark
                )
                VALUES (%s, %s, 'system', 'aicrm_next_seed', %s, %s, 'masked local automation readonly sample')
                """,
                (
                    member_id,
                    SAMPLE["event_action"],
                    Jsonb({}),
                    Jsonb({"current_pool": SAMPLE["current_pool"], "current_audience_code": SAMPLE["current_audience_code"]}),
                ),
            )

            cur.execute(
                """
                INSERT INTO automation_workflow (
                    program_id, workflow_code, workflow_name, description, status, enabled, created_by, updated_by
                )
                VALUES (%s, %s, 'workflow_masked_001', 'masked local workflow shell; not executed', 'active', FALSE,
                        'aicrm_next_seed', 'aicrm_next_seed')
                ON CONFLICT (workflow_code) DO UPDATE SET
                    program_id = EXCLUDED.program_id,
                    workflow_name = EXCLUDED.workflow_name,
                    status = EXCLUDED.status,
                    enabled = FALSE,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = NOW()
                RETURNING id
                """,
                (program_id, SAMPLE["workflow_code"]),
            )
            workflow_id = int(cur.fetchone()[0])

            cur.execute(
                """
                INSERT INTO automation_workflow_node (
                    workflow_id, node_code, node_name, target_audience_code, trigger_mode, day_offset, send_time, enabled
                )
                VALUES (%s, %s, 'node_masked_001', %s, 'scheduled', 1, '09:00', FALSE)
                ON CONFLICT (workflow_id, node_code) DO UPDATE SET
                    node_name = EXCLUDED.node_name,
                    target_audience_code = EXCLUDED.target_audience_code,
                    enabled = FALSE,
                    updated_at = NOW()
                RETURNING id
                """,
                (workflow_id, SAMPLE["node_code"], SAMPLE["current_audience_code"]),
            )
            node_id = int(cur.fetchone()[0])

            cur.execute(
                """
                INSERT INTO automation_workflow_execution (
                    execution_id, program_id, workflow_id, node_id, trigger_type, audience_code,
                    scheduled_for, status, total_count, success_count, skipped_count, failed_count, summary_json, finished_at
                )
                VALUES (%s, %s, %s, %s, 'debug', %s, %s, 'finished', 1, 1, 0, 0, %s, %s)
                RETURNING id
                """,
                (
                    SAMPLE["execution_id"],
                    program_id,
                    workflow_id,
                    node_id,
                    SAMPLE["current_audience_code"],
                    now,
                    Jsonb({"source": "aicrm_next_local_masked_automation_sample", "runtime_executed": False}),
                    now,
                ),
            )
            execution_pk = int(cur.fetchone()[0])
            cur.execute(
                """
                INSERT INTO automation_workflow_execution_item (
                    execution_id, workflow_id, node_id, member_id, external_contact_id, rendered_content_text,
                    content_snapshot_json, status, trace_id
                )
                VALUES (%s, %s, %s, %s, %s, 'content_masked_automation_001', %s, 'prepared', 'trace_masked_automation_001')
                """,
                (
                    execution_pk,
                    workflow_id,
                    node_id,
                    member_id,
                    SAMPLE["external_userid"],
                    Jsonb({"masked": True, "runtime_executed": False}),
                ),
            )

        conn.commit()
    return {"ok": True, "dry_run": False, "member_id": member_id, "program_id": program_id, **plan}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed masked Automation sample rows into local old Flask test DB.")
    parser.add_argument("--database-url", default=os.environ.get("OLD_FLASK_TEST_DATABASE_URL", ""))
    parser.add_argument("--apply", action="store_true", help="Apply writes. Omit for dry-run.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = seed_sample(args.database_url, apply=bool(args.apply))
    print(f"safe_url: {result['redacted_url']}")
    print(f"database: {result['database']}")
    print(f"host: {result['host']}")
    print(f"apply: {result['apply']}")
    print(f"sample_external_userid: {result['sample']['external_userid']}")
    print(f"sample_member_external_id: {result['sample']['member_external_id']}")
    if not args.apply:
        print("dry_run: true")
    else:
        print(f"seeded_member_id: {result['member_id']}")
        print(f"seeded_program_id: {result['program_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
