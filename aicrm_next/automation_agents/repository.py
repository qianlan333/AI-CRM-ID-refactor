from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from aicrm_next.shared.db_session import get_session_factory


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str, separators=(",", ":"))


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _public_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    payload = dict(row)
    for key, value in list(payload.items()):
        if key.endswith("_json"):
            payload[key] = _json_obj(value)
        elif isinstance(value, datetime):
            payload[key] = value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return payload


class AutomationAgentRepository:
    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    def _one(self, statement: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.execute(text(statement), params or {}).mappings().fetchone()
            return _public_row(dict(row)) if row else None

    def _all(self, statement: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.execute(text(statement), params or {}).mappings().fetchall()
            return [_public_row(dict(row)) or {} for row in rows]

    def _write_one(self, statement: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.execute(text(statement), params or {}).mappings().fetchone()
            session.commit()
            return _public_row(dict(row)) if row else None

    def _write_all(self, statement: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.execute(text(statement), params or {}).mappings().fetchall()
            session.commit()
            return [_public_row(dict(row)) or {} for row in rows]

    def list_agents(self, *, limit: int = 200) -> list[dict[str, Any]]:
        return self._all(
            """
            SELECT a.*,
                   p.name AS bound_package_name,
                   COUNT(*) OVER () AS total_count
            FROM automation_agent_runtime_config a
            LEFT JOIN ai_audience_package p ON p.package_key = a.bound_package_key
            WHERE a.status <> 'archived'
            ORDER BY a.updated_at DESC, a.id DESC
            LIMIT :limit
            """,
            {"limit": max(1, min(int(limit or 200), 200))},
        )

    def get_agent(self, agent_id: int) -> dict[str, Any] | None:
        return self._one(
            """
            SELECT a.*, p.name AS bound_package_name
            FROM automation_agent_runtime_config a
            LEFT JOIN ai_audience_package p ON p.package_key = a.bound_package_key
            WHERE a.id = :agent_id
            LIMIT 1
            """,
            {"agent_id": int(agent_id)},
        )

    def get_agent_by_code(self, agent_code: str) -> dict[str, Any] | None:
        return self._one(
            """
            SELECT a.*, p.name AS bound_package_name
            FROM automation_agent_runtime_config a
            LEFT JOIN ai_audience_package p ON p.package_key = a.bound_package_key
            WHERE a.agent_code = :agent_code
              AND a.status <> 'archived'
            ORDER BY a.id DESC
            LIMIT 1
            """,
            {"agent_code": _text(agent_code)},
        )

    def get_package_by_key(self, package_key: str) -> dict[str, Any] | None:
        return self._one(
            "SELECT * FROM ai_audience_package WHERE package_key = :package_key LIMIT 1",
            {"package_key": _text(package_key)},
        )

    def create_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = self._write_one(
            """
            INSERT INTO automation_agent_runtime_config (
                agent_code, agent_name, bound_package_key, status,
                draft_role_prompt, draft_task_prompt, published_role_prompt, published_task_prompt,
                draft_version, published_version, fixed_content_package_json, inbound_webhook_secret,
                created_at, updated_at
            ) VALUES (
                :agent_code, :agent_name, :bound_package_key, :status,
                :role_prompt, :task_prompt, :role_prompt, :task_prompt,
                1, 1, CAST(:fixed_content_package_json AS jsonb), :inbound_webhook_secret,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING *
            """,
            {
                "agent_code": _text(payload.get("agent_code")),
                "agent_name": _text(payload.get("agent_name")),
                "bound_package_key": _text(payload.get("bound_package_key")),
                "status": _text(payload.get("status")) or "active",
                "role_prompt": _text(payload.get("role_prompt")),
                "task_prompt": _text(payload.get("task_prompt")),
                "fixed_content_package_json": _json_dumps(payload.get("fixed_content_package") or {}),
                "inbound_webhook_secret": _text(payload.get("inbound_webhook_secret")) or uuid4().hex,
            },
        )
        if not row:
            raise RuntimeError("automation agent create failed")
        return row

    def update_agent(self, agent_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.get_agent(agent_id)
        if not existing:
            return None
        merged = {
            "agent_name": _text(payload.get("agent_name")) if "agent_name" in payload else _text(existing.get("agent_name")),
            "bound_package_key": _text(payload.get("bound_package_key")) if "bound_package_key" in payload else _text(existing.get("bound_package_key")),
            "status": _text(payload.get("status")) if "status" in payload else _text(existing.get("status")),
            "role_prompt": _text(payload.get("role_prompt")) if "role_prompt" in payload else _text(existing.get("draft_role_prompt")),
            "task_prompt": _text(payload.get("task_prompt")) if "task_prompt" in payload else _text(existing.get("draft_task_prompt")),
            "fixed_content_package": (
                payload.get("fixed_content_package")
                if "fixed_content_package" in payload
                else existing.get("fixed_content_package_json") or {}
            ),
        }
        return self._write_one(
            """
            UPDATE automation_agent_runtime_config
            SET agent_name = :agent_name,
                bound_package_key = :bound_package_key,
                status = :status,
                draft_role_prompt = :role_prompt,
                draft_task_prompt = :task_prompt,
                published_role_prompt = :role_prompt,
                published_task_prompt = :task_prompt,
                draft_version = draft_version + 1,
                published_version = published_version + 1,
                fixed_content_package_json = CAST(:fixed_content_package_json AS jsonb),
                archived_at = CASE WHEN :status = 'archived' THEN COALESCE(archived_at, CURRENT_TIMESTAMP) ELSE archived_at END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :agent_id
            RETURNING *
            """,
            {
                "agent_id": int(agent_id),
                "agent_name": merged["agent_name"],
                "bound_package_key": merged["bound_package_key"],
                "status": merged["status"] or "active",
                "role_prompt": merged["role_prompt"],
                "task_prompt": merged["task_prompt"],
                "fixed_content_package_json": _json_dumps(merged["fixed_content_package"]),
            },
        )

    def set_status(self, agent_id: int, status: str) -> dict[str, Any] | None:
        return self._write_one(
            """
            UPDATE automation_agent_runtime_config
            SET status = :status,
                archived_at = CASE WHEN :status = 'archived' THEN COALESCE(archived_at, CURRENT_TIMESTAMP) ELSE archived_at END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :agent_id
            RETURNING *
            """,
            {"agent_id": int(agent_id), "status": _text(status)},
        )

    def next_copy_code(self, agent_code: str) -> str:
        base = f"{_text(agent_code)}_copy"
        rows = self._all(
            """
            SELECT agent_code
            FROM automation_agent_runtime_config
            WHERE agent_code LIKE :prefix
            """,
            {"prefix": f"{base}_%"},
        )
        existing = {_text(row.get("agent_code")) for row in rows}
        for index in range(1, 1000):
            candidate = f"{base}_{index:03d}"
            if candidate not in existing:
                return candidate
        raise RuntimeError("agent copy code exhausted")

    def create_batch(
        self,
        *,
        batch_id: str,
        agent: dict[str, Any],
        headers: dict[str, Any],
        payload: Any,
        external_userids: list[str],
        received_count: int,
        idempotency_key: str,
        source_event_type: str,
        refresh_run_id: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        deduped_count = len(external_userids)
        with self._session_factory() as session:
            row = session.execute(
                text(
                    """
                    INSERT INTO automation_agent_webhook_batch (
                        batch_id, agent_code, bound_package_key, source_event_type, refresh_run_id,
                        idempotency_key, received_count, deduped_count, accepted_count, status,
                        request_headers_json, request_payload_json, created_at
                    ) VALUES (
                        :batch_id, :agent_code, :bound_package_key, :source_event_type, :refresh_run_id,
                        :idempotency_key, :received_count, :deduped_count, :accepted_count, 'queued',
                        CAST(:headers_json AS jsonb), CAST(:payload_json AS jsonb), CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (idempotency_key) WHERE idempotency_key <> ''
                    DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                    RETURNING *
                    """
                ),
                {
                    "batch_id": batch_id,
                    "agent_code": _text(agent.get("agent_code")),
                    "bound_package_key": _text(agent.get("bound_package_key")),
                    "source_event_type": source_event_type,
                    "refresh_run_id": refresh_run_id,
                    "idempotency_key": idempotency_key,
                    "received_count": int(received_count),
                    "deduped_count": deduped_count,
                    "accepted_count": deduped_count,
                    "headers_json": _json_dumps(headers),
                    "payload_json": _json_dumps(payload),
                },
            ).mappings().one()
            batch = dict(row)
            rows: list[dict[str, Any]] = []
            for external_userid in external_userids:
                external_event_id = f"agent:{agent['agent_code']}:{external_userid}:{batch['batch_id']}"
                item = session.execute(
                    text(
                        """
                        INSERT INTO automation_agent_webhook_item (
                            batch_id, agent_code, external_userid, external_event_id, status, created_at
                        ) VALUES (
                            :batch_id, :agent_code, :external_userid, :external_event_id, 'queued', CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (batch_id, external_userid) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                        RETURNING *
                        """
                    ),
                    {
                        "batch_id": _text(batch["batch_id"]),
                        "agent_code": _text(agent.get("agent_code")),
                        "external_userid": external_userid,
                        "external_event_id": external_event_id,
                    },
                ).mappings().one()
                rows.append(_public_row(dict(item)) or {})
            session.commit()
        return _public_row(batch) or {}, rows

    def list_queued_items(self, batch_id: str) -> list[dict[str, Any]]:
        return self._all(
            """
            SELECT * FROM automation_agent_webhook_item
            WHERE batch_id = :batch_id
              AND status IN ('queued', 'failed_retryable')
            ORDER BY id ASC
            """,
            {"batch_id": _text(batch_id)},
        )

    def mark_batch_status(self, batch_id: str, status: str) -> None:
        self._write_one(
            """
            UPDATE automation_agent_webhook_batch
            SET status = :status,
                started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                finished_at = CASE WHEN :status IN ('succeeded', 'partial_failed', 'failed') THEN CURRENT_TIMESTAMP ELSE finished_at END,
                updated_at = CURRENT_TIMESTAMP
            WHERE batch_id = :batch_id
            RETURNING *
            """,
            {"batch_id": _text(batch_id), "status": _text(status)},
        )

    def update_item(self, item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "owner_userid",
            "status",
            "context_snapshot_json",
            "prompt_preview",
            "raw_agent_output",
            "content_package_json",
            "callback_payload_json",
            "callback_status",
            "callback_response_json",
            "error_code",
            "error_message",
            "started_at",
            "finished_at",
        }
        columns = [key for key in payload if key in allowed]
        if not columns:
            return self._one("SELECT * FROM automation_agent_webhook_item WHERE id = :id", {"id": int(item_id)}) or {}
        params: dict[str, Any] = {"id": int(item_id)}
        assignments: list[str] = []
        for index, column in enumerate(columns):
            name = f"p{index}"
            value = payload[column]
            if column.endswith("_json"):
                assignments.append(f"{column} = CAST(:{name} AS jsonb)")
                params[name] = _json_dumps(value)
            elif column in {"started_at", "finished_at"} and value == "now":
                assignments.append(f"{column} = CURRENT_TIMESTAMP")
            else:
                assignments.append(f"{column} = :{name}")
                params[name] = value
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        return self._write_one(
            f"UPDATE automation_agent_webhook_item SET {', '.join(assignments)} WHERE id = :id RETURNING *",
            params,
        ) or {}


def build_automation_agent_repository() -> AutomationAgentRepository:
    return AutomationAgentRepository()

