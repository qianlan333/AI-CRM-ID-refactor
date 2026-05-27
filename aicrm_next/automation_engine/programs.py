from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, create_engine, text

from aicrm_next.shared.runtime import production_data_ready, raw_database_url


class AutomationProgramDataUnavailable(RuntimeError):
    pass


SETUP_STEPS: tuple[dict[str, str], ...] = (
    {"key": "basic", "label": "基础信息"},
    {"key": "entry", "label": "入口渠道"},
    {"key": "segmentation", "label": "分层规则"},
    {"key": "entry-rule", "label": "入池规则"},
    {"key": "operations", "label": "运营编排"},
    {"key": "publish", "label": "检查并发布"},
)


_FIXTURE_PROGRAM = {
    "id": 1,
    "program_name": "自动化运营方案",
    "program_code": "next_local_preview",
    "description": "本地结构校验方案；生产环境读取 PostgreSQL。",
    "status": "active",
    "updated_at": "2026-05-20T12:00:00Z",
    "config_json": {},
}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return deepcopy(value)
    if value is None:
        return deepcopy(default)
    text_value = str(value or "").strip()
    if not text_value:
        return deepcopy(default)
    try:
        return json.loads(text_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return deepcopy(default)


def _json_text(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def _stringify_datetime(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _sqlalchemy_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _program_summary(program: dict[str, Any], summary: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = dict(summary or {})
    publish_state = dict(summary.get("publish_state") or {})
    full_published = bool(publish_state.get("full_published"))
    entry_published = bool(publish_state.get("entry_published"))
    publish_status = "full" if full_published else "entry" if entry_published else "unpublished"
    publish_label = "完整自动化已发布" if full_published else "入口已发布" if entry_published else "未发布"
    return {
        "channel_count": int(summary.get("channel_count") or 0),
        "workflow_count": int(summary.get("workflow_count") or 0),
        "latest_execution_at": _clean_text(summary.get("latest_execution_at")),
        "publish_state": publish_state,
        "publish_status": publish_status,
        "publish_status_label": publish_label,
    }


def _fixture_summary() -> dict[str, Any]:
    return _program_summary(
        _FIXTURE_PROGRAM,
        {
            "channel_count": 1,
            "workflow_count": 0,
            "latest_execution_at": "",
            "publish_state": {},
        },
    )


def _fixture_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "items": [{"program": deepcopy(_FIXTURE_PROGRAM), "summary": _fixture_summary()}],
        "default_program": {"id": _FIXTURE_PROGRAM["id"], "program_name": _FIXTURE_PROGRAM["program_name"]},
        "total": 1,
        "source_status": "next_local_preview",
    }


class PostgresAutomationProgramRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_payload(self) -> dict[str, Any]:
        rows = self._fetch_program_rows()
        items = [{"program": row["program"], "summary": row["summary"]} for row in rows]
        default = next((item["program"] for item in items if item["program"].get("program_code") == "signup_conversion_v1"), None)
        if default is None and items:
            default = items[0]["program"]
        return {
            "ok": True,
            "items": items,
            "default_program": {"id": default.get("id"), "program_name": default.get("program_name")} if default else {},
            "total": len(items),
            "source_status": "next_postgres",
        }

    def get_program_with_summary(self, program_id: int) -> dict[str, Any] | None:
        rows = self._fetch_program_rows(program_id=int(program_id))
        return rows[0] if rows else None

    def copy_program(self, program_id: int, *, operator_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(payload or {})
        with self._engine.begin() as conn:
            source = conn.execute(
                text("SELECT * FROM automation_program WHERE id = :program_id LIMIT 1"),
                {"program_id": int(program_id)},
            ).mappings().first()
            if not source:
                raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
            source_dict = dict(source)
            timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
            program_name = _clean_text(payload.get("program_name")) or f"{source_dict.get('program_name') or '自动化运营方案'} 副本"
            program_code = _clean_text(payload.get("program_code")) or f"{source_dict.get('program_code') or 'program'}_copy_{timestamp}"
            inserted = conn.execute(
                text(
                    """
                    INSERT INTO automation_program (
                        program_code,
                        program_name,
                        description,
                        status,
                        config_json,
                        created_by,
                        updated_by,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :program_code,
                        :program_name,
                        :description,
                        'draft',
                        CAST(:config_json AS jsonb),
                        :operator_id,
                        :operator_id,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                    RETURNING *
                    """
                ),
                {
                    "program_code": program_code,
                    "program_name": program_name,
                    "description": _clean_text(source_dict.get("description")),
                    "config_json": _json_text(_json_loads(source_dict.get("config_json"), default={})),
                    "operator_id": _clean_text(operator_id),
                },
            ).mappings().first()
            if not inserted:
                raise AutomationProgramDataUnavailable("automation program copy insert failed")
            target_id = int(inserted["id"])
            blocks = conn.execute(
                text(
                    """
                    SELECT *
                    FROM automation_program_config_block
                    WHERE program_id = :program_id
                    ORDER BY block_key ASC
                    """
                ),
                {"program_id": int(program_id)},
            ).mappings().all()
            for block in blocks:
                block_dict = dict(block)
                block_payload = _json_loads(block_dict.get("payload_json"), default={})
                if _clean_text(block_dict.get("block_key")) == "entry_channel":
                    qrcode = dict(block_payload.get("qrcode") or {})
                    for key in ("qr_ticket", "qr_url", "scene_value", "config_id", "wecom_response"):
                        qrcode.pop(key, None)
                    block_payload["qrcode"] = qrcode
                    block_payload.pop("customer_acquisition_link_ids", None)
                conn.execute(
                    text(
                        """
                        INSERT INTO automation_program_config_block (
                            program_id,
                            block_key,
                            payload_json,
                            status,
                            version,
                            copied_from_program_id,
                            copied_from_block_id,
                            created_at,
                            updated_at
                        )
                        VALUES (
                            :target_id,
                            :block_key,
                            CAST(:payload_json AS jsonb),
                            :status,
                            1,
                            :source_program_id,
                            :source_block_id,
                            CURRENT_TIMESTAMP,
                            CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "target_id": target_id,
                        "block_key": _clean_text(block_dict.get("block_key")),
                        "payload_json": _json_text(block_payload),
                        "status": _clean_text(block_dict.get("status")) or "draft",
                        "source_program_id": int(program_id),
                        "source_block_id": int(block_dict.get("id") or 0),
                    },
                )
        copied = self.get_program_with_summary(target_id)
        if not copied:
            raise AutomationProgramDataUnavailable(f"copied automation program {target_id} not found")
        return copied

    def update_basic_info(self, program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
        status = _clean_text(payload.get("status")) or "draft"
        if status not in {"draft", "active", "paused", "archived"}:
            status = "draft"
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    UPDATE automation_program
                    SET program_name = :program_name,
                        program_code = :program_code,
                        description = :description,
                        status = :status,
                        updated_by = :operator_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :program_id
                    RETURNING *
                    """
                ),
                {
                    "program_id": int(program_id),
                    "program_name": _clean_text(payload.get("program_name")),
                    "program_code": _clean_text(payload.get("program_code")),
                    "description": _clean_text(payload.get("description")),
                    "status": status,
                    "operator_id": _clean_text(operator_id),
                },
            ).mappings().first()
        if not row:
            raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
        updated = self.get_program_with_summary(int(program_id))
        if not updated:
            raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
        return updated

    def update_status(self, program_id: int, *, status: str, operator_id: str) -> dict[str, Any]:
        if status not in {"draft", "active", "paused", "archived"}:
            raise AutomationProgramDataUnavailable(f"unsupported automation program status: {status}")
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    UPDATE automation_program
                    SET status = :status,
                        updated_by = :operator_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :program_id
                    RETURNING id
                    """
                ),
                {"program_id": int(program_id), "status": status, "operator_id": _clean_text(operator_id)},
            ).mappings().first()
        if not row:
            raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
        updated = self.get_program_with_summary(int(program_id))
        if not updated:
            raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
        return updated

    def _fetch_program_rows(self, *, program_id: int | None = None) -> list[dict[str, Any]]:
        where_sql = "WHERE p.id = :program_id" if program_id is not None else "WHERE 1 = 1"
        params = {"program_id": int(program_id)} if program_id is not None else {}
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT
                        p.*,
                        COALESCE(bindings.channel_count, 0) AS channel_count,
                        COALESCE(workflows.workflow_count, 0) AS workflow_count,
                        executions.latest_execution_at AS latest_execution_at,
                        publish_state.payload_json AS publish_state
                    FROM automation_program p
                    LEFT JOIN LATERAL (
                        SELECT COUNT(*) AS channel_count
                        FROM automation_program_channel_binding b
                        WHERE b.program_id = p.id
                          AND b.binding_status <> 'archived'
                    ) bindings ON true
                    LEFT JOIN LATERAL (
                        SELECT COUNT(*) AS workflow_count
                        FROM automation_workflow w
                        WHERE w.program_id = p.id
                          AND w.status <> 'archived'
                    ) workflows ON true
                    LEFT JOIN LATERAL (
                        SELECT MAX(COALESCE(CAST(e.scheduled_for AS TEXT), CAST(e.updated_at AS TEXT), CAST(e.created_at AS TEXT), '')) AS latest_execution_at
                        FROM automation_workflow_execution e
                        WHERE e.program_id = p.id
                    ) executions ON true
                    LEFT JOIN automation_program_config_block publish_state
                      ON publish_state.program_id = p.id
                     AND publish_state.block_key = 'publish_state'
                    {where_sql}
                    ORDER BY
                        CASE p.status
                            WHEN 'active' THEN 0
                            WHEN 'draft' THEN 1
                            WHEN 'paused' THEN 2
                            ELSE 3
                        END,
                        p.updated_at DESC,
                        p.id DESC
                    """
                ),
                params,
            ).mappings().all()
        return [self._project_row(dict(row)) for row in rows]

    def _project_row(self, row: dict[str, Any]) -> dict[str, Any]:
        program = {
            "id": int(row.get("id") or 0),
            "program_code": _clean_text(row.get("program_code")),
            "program_name": _clean_text(row.get("program_name")),
            "description": _clean_text(row.get("description")),
            "status": _clean_text(row.get("status")) or "draft",
            "config_json": _json_loads(row.get("config_json"), default={}),
            "created_by": _clean_text(row.get("created_by")),
            "updated_by": _clean_text(row.get("updated_by")),
            "created_at": _stringify_datetime(row.get("created_at")),
            "updated_at": _stringify_datetime(row.get("updated_at")),
        }
        summary = _program_summary(
            program,
            {
                "channel_count": row.get("channel_count"),
                "workflow_count": row.get("workflow_count"),
                "latest_execution_at": row.get("latest_execution_at"),
                "publish_state": _json_loads(row.get("publish_state"), default={}),
            },
        )
        return {"program": program, "summary": summary}


def _build_postgres_repository() -> PostgresAutomationProgramRepository:
    database_url = raw_database_url()
    if not database_url:
        raise AutomationProgramDataUnavailable("DATABASE_URL is required for automation program repository")
    return PostgresAutomationProgramRepository(create_engine(_sqlalchemy_database_url(database_url), future=True))


def list_automation_programs_payload() -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().list_payload()
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    return _fixture_payload()


def get_automation_program_with_summary(program_id: int) -> dict[str, Any] | None:
    if production_data_ready():
        try:
            return _build_postgres_repository().get_program_with_summary(int(program_id))
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    if int(program_id) == int(_FIXTURE_PROGRAM["id"]):
        return {"program": deepcopy(_FIXTURE_PROGRAM), "summary": _fixture_summary()}
    return None


def copy_automation_program(program_id: int, *, operator_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().copy_program(int(program_id), operator_id=operator_id, payload=payload)
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    copied_program = deepcopy(_FIXTURE_PROGRAM)
    copied_program["id"] = int(program_id) + 1000
    copied_program["program_name"] = _clean_text((payload or {}).get("program_name")) or f"{copied_program['program_name']} 副本"
    copied_program["program_code"] = _clean_text((payload or {}).get("program_code")) or f"{copied_program['program_code']}_copy"
    copied_program["status"] = "draft"
    copied_program["updated_at"] = datetime.now(UTC).isoformat()
    return {"program": copied_program, "summary": _fixture_summary()}


def update_automation_program_basic_info(program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().update_basic_info(int(program_id), payload, operator_id=operator_id)
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    updated = deepcopy(_FIXTURE_PROGRAM)
    updated["id"] = int(program_id)
    updated["program_name"] = _clean_text(payload.get("program_name")) or updated["program_name"]
    updated["program_code"] = _clean_text(payload.get("program_code")) or updated["program_code"]
    updated["description"] = _clean_text(payload.get("description"))
    updated["status"] = _clean_text(payload.get("status")) or updated["status"]
    return {"program": updated, "summary": _fixture_summary()}


def update_automation_program_status(program_id: int, *, status: str, operator_id: str) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().update_status(int(program_id), status=status, operator_id=operator_id)
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    updated = deepcopy(_FIXTURE_PROGRAM)
    updated["id"] = int(program_id)
    updated["status"] = status
    return {"program": updated, "summary": _fixture_summary()}
