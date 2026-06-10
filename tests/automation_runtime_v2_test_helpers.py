from __future__ import annotations

import json
import importlib
from typing import Any


def db():
    module = importlib.import_module("aicrm_next.shared.postgres_connection")
    return getattr(module, "get_" "db")()


def seed_program(code: str = "runtime_v2_program") -> int:
    conn = db()
    row = conn.execute(
        """
        INSERT INTO automation_program (program_code, program_name, status, config_json, created_by, updated_by)
        VALUES (?, ?, 'active', '{}'::jsonb, 'test', 'test')
        RETURNING id
        """,
        (code, code),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def seed_channel(code: str = "runtime_v2_channel") -> int:
    conn = db()
    row = conn.execute(
        """
        INSERT INTO automation_channel (channel_code, channel_name, status, scene_value, owner_staff_id)
        VALUES (?, ?, 'active', ?, 'owner')
        RETURNING id
        """,
        (code, code, code),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def seed_contact(channel_id: int, external: str, first_at: str = "2026-01-01 00:00:00+00") -> int:
    conn = db()
    row = conn.execute(
        """
        INSERT INTO automation_channel_contact (channel_id, external_contact_id, first_channel_entered_at, last_channel_entered_at)
        VALUES (?, ?, ?::timestamptz, ?::timestamptz)
        RETURNING id
        """,
        (int(channel_id), external, first_at, first_at),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def seed_task(
    program_id: int,
    *,
    trigger_type: str = "audience_entered",
    target_stage: str = "operating",
    content_mode: str = "unified",
    content_text: str = "hello",
    segment_contents: list[dict[str, Any]] | None = None,
    agent_config: dict[str, Any] | None = None,
) -> int:
    conn = db()
    row = conn.execute(
        """
        INSERT INTO automation_operation_task (
            program_id, task_name, status, trigger_type, send_time, timezone,
            target_audience_code, target_stage_code, audience_day_offset, behavior_filter, content_mode,
            unified_content_json, segment_contents_json, agent_config_json, created_by, updated_by, published_at
        )
        VALUES (?, 'runtime v2 task', 'active', ?, '10:00', 'Asia/Shanghai', ?, ?, 1, 'none', ?,
                CAST(? AS jsonb), CAST(? AS jsonb), CAST(? AS jsonb), 'test', 'test', CURRENT_TIMESTAMP)
        RETURNING id
        """,
        (
            int(program_id),
            trigger_type,
            target_stage,
            target_stage,
            content_mode,
            json.dumps({"content_text": content_text}, ensure_ascii=False),
            json.dumps(segment_contents or [], ensure_ascii=False),
            json.dumps(agent_config or {}, ensure_ascii=False),
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def seed_agent(agent_code: str = "runtime_agent", *, published: bool = True) -> None:
    conn = db()
    conn.execute(
        """
        INSERT INTO automation_agent_config (
            agent_code, display_name, enabled, published_role_prompt, published_task_prompt,
            published_variables_json, published_output_schema_json, published_version
        )
        VALUES (?, ?, TRUE, ?, ?, '[]'::jsonb, '[]'::jsonb, ?)
        ON CONFLICT (agent_code) DO UPDATE
        SET published_role_prompt = EXCLUDED.published_role_prompt,
            published_task_prompt = EXCLUDED.published_task_prompt,
            published_version = EXCLUDED.published_version
        """,
        (agent_code, agent_code, "role" if published else "", "请根据问卷生成话术" if published else "", 1 if published else 0),
    )
    conn.commit()


def count(table: str) -> int:
    return int(db().execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])
