from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.repository_provider import RepositoryProviderError

from .domain import clean_text, generate_webhook_key, generate_webhook_token, hash_webhook_token, normalize_plan_payload


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _json_loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return deepcopy(default)
    if isinstance(value, (dict, list)):
        return deepcopy(value)
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return deepcopy(default)


def _as_mapping(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    mapping = getattr(row, "_mapping", None)
    return dict(mapping or row)


def _iso(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class PostgresGroupOpsRepository:
    source_status = "postgres_group_ops_repository"

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_plans(self, filters: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
        keyword = clean_text(filters.get("keyword")).lower()
        plan_type = clean_text(filters.get("plan_type")).lower()
        status = clean_text(filters.get("status")).lower()
        clauses = ["(archived_at IS NULL)"]
        params: dict[str, Any] = {
            "keyword": f"%{keyword}%",
            "plan_type": plan_type,
            "status": status,
            "limit": max(1, _int(filters.get("limit")) or 50),
            "offset": max(0, _int(filters.get("offset"))),
        }
        if keyword:
            clauses.append("(LOWER(plan_name) LIKE :keyword OR LOWER(plan_code) LIKE :keyword OR LOWER(owner_userid) LIKE :keyword)")
        if plan_type:
            clauses.append("plan_type = :plan_type")
        if status:
            clauses.append("status = :status")
        where = f"WHERE {' AND '.join(clauses)}"
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    text(
                        f"""
                        SELECT *
                        FROM automation_group_ops_plans
                        {where}
                        ORDER BY id ASC
                        LIMIT :limit OFFSET :offset
                        """
                    ),
                    params,
                ).fetchall()
                total = conn.execute(
                    text(f"SELECT COUNT(*) AS total FROM automation_group_ops_plans {where}"),
                    {key: value for key, value in params.items() if key not in {"limit", "offset"}},
                ).scalar_one()
                return [self._row_to_plan(conn, _as_mapping(row) or {}) for row in rows], int(total or 0)
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def get_plan(self, plan_id: int) -> dict[str, Any] | None:
        try:
            with self._engine.connect() as conn:
                return self._get_plan_sql(conn, int(plan_id))
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def get_plan_by_webhook_key(self, webhook_key: str) -> dict[str, Any] | None:
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT *
                        FROM automation_group_ops_plans
                        WHERE webhook_key = :webhook_key
                          AND archived_at IS NULL
                        LIMIT 1
                        """
                    ),
                    {"webhook_key": clean_text(webhook_key)},
                ).fetchone()
                return self._row_to_plan(conn, _as_mapping(row)) if row else None
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def create_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_plan_payload(payload)
        webhook_key = ""
        webhook_token_hash = ""
        if normalized["plan_type"] == "webhook":
            webhook_key = generate_webhook_key(normalized["plan_name"])
            webhook_token_hash = hash_webhook_token(generate_webhook_token())
        try:
            with self._engine.begin() as conn:
                row = conn.execute(
                    text(
                        """
                        INSERT INTO automation_group_ops_plans (
                            plan_code, plan_name, plan_type, owner_userid, status,
                            webhook_key, webhook_token_hash, created_by, updated_by
                        )
                        VALUES (
                            :plan_code, :plan_name, :plan_type, :owner_userid, :status,
                            :webhook_key, :webhook_token_hash, :created_by, :updated_by
                        )
                        RETURNING id
                        """
                    ),
                    {
                        **normalized,
                        "webhook_key": webhook_key,
                        "webhook_token_hash": webhook_token_hash,
                    },
                ).fetchone()
                plan_id = int((_as_mapping(row) or {}).get("id") or 0)
                if not normalized["plan_code"]:
                    conn.execute(
                        text("UPDATE automation_group_ops_plans SET plan_code = :plan_code WHERE id = :plan_id"),
                        {"plan_code": f"group_plan_{plan_id:03d}", "plan_id": plan_id},
                    )
                return self._get_plan_sql(conn, plan_id) or {}
        except IntegrityError as exc:
            raise ContractError("group ops plan code or webhook key already exists") from exc
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def update_plan(self, plan_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            with self._engine.begin() as conn:
                current = self._get_plan_sql(conn, int(plan_id))
                if not current:
                    raise NotFoundError("group ops plan not found")
                normalized = normalize_plan_payload(payload, existing=current)
                conn.execute(
                    text(
                        """
                        UPDATE automation_group_ops_plans
                        SET plan_code = :plan_code,
                            plan_name = :plan_name,
                            plan_type = :plan_type,
                            owner_userid = :owner_userid,
                            status = :status,
                            updated_by = :updated_by,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :plan_id
                        """
                    ),
                    {**normalized, "plan_code": normalized["plan_code"] or current["plan_code"], "plan_id": int(plan_id)},
                )
                return self._get_plan_sql(conn, int(plan_id)) or {}
        except NotFoundError:
            raise
        except IntegrityError as exc:
            raise ContractError("group ops plan code already exists") from exc
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def list_bound_groups(self, plan_id: int) -> list[dict[str, Any]]:
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT *
                        FROM automation_group_ops_plan_groups
                        WHERE plan_id = :plan_id
                          AND status = 'active'
                        ORDER BY id ASC
                        """
                    ),
                    {"plan_id": int(plan_id)},
                ).fetchall()
                return [self._row_to_plan_group(_as_mapping(row) or {}) for row in rows]
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def bind_group(self, plan_id: int, group: dict[str, Any]) -> dict[str, Any]:
        chat_id = clean_text(group.get("chat_id"))
        try:
            with self._engine.begin() as conn:
                existing = conn.execute(
                    text(
                        """
                        SELECT id
                        FROM automation_group_ops_plan_groups
                        WHERE plan_id = :plan_id AND chat_id = :chat_id
                        LIMIT 1
                        """
                    ),
                    {"plan_id": int(plan_id), "chat_id": chat_id},
                ).fetchone()
                if existing:
                    binding_id = int((_as_mapping(existing) or {}).get("id") or 0)
                    conn.execute(
                        text(
                            """
                            UPDATE automation_group_ops_plan_groups
                            SET group_name_snapshot = :group_name,
                                owner_userid_snapshot = :owner_userid,
                                internal_member_count_snapshot = :internal_count,
                                external_member_count_snapshot = :external_count,
                                status = 'active',
                                removed_at = NULL
                            WHERE id = :binding_id
                            """
                        ),
                        self._group_binding_params(binding_id=binding_id, group=group),
                    )
                else:
                    row = conn.execute(
                        text(
                            """
                            INSERT INTO automation_group_ops_plan_groups (
                                plan_id, chat_id, group_name_snapshot, owner_userid_snapshot,
                                internal_member_count_snapshot, external_member_count_snapshot, status
                            )
                            VALUES (
                                :plan_id, :chat_id, :group_name, :owner_userid,
                                :internal_count, :external_count, 'active'
                            )
                            RETURNING id
                            """
                        ),
                        {"plan_id": int(plan_id), "chat_id": chat_id, **self._group_binding_params(group=group)},
                    ).fetchone()
                    binding_id = int((_as_mapping(row) or {}).get("id") or 0)
                return self._get_plan_group_sql(conn, binding_id) or {}
        except IntegrityError as exc:
            raise ContractError("group is already bound to this plan") from exc
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def remove_group(self, plan_id: int, chat_id: str) -> bool:
        try:
            with self._engine.begin() as conn:
                result = conn.execute(
                    text(
                        """
                        UPDATE automation_group_ops_plan_groups
                        SET status = 'removed', removed_at = CURRENT_TIMESTAMP
                        WHERE plan_id = :plan_id
                          AND chat_id = :chat_id
                          AND status = 'active'
                        """
                    ),
                    {"plan_id": int(plan_id), "chat_id": clean_text(chat_id)},
                )
                return bool(result.rowcount)
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def list_group_assets(self, filters: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
        keyword = clean_text(filters.get("keyword")).lower()
        owner_userid = clean_text(filters.get("owner_userid"))
        plan_id = _int(filters.get("plan_id"))
        bind_status = clean_text(filters.get("bind_status")).lower()
        clauses = ["g.status = 'active'"]
        join_extra = "AND pg.plan_id = :filter_plan_id" if plan_id else ""
        params: dict[str, Any] = {
            "keyword": f"%{keyword}%",
            "owner_userid": owner_userid,
            "filter_plan_id": plan_id,
            "limit": max(1, _int(filters.get("limit")) or 50),
            "offset": max(0, _int(filters.get("offset"))),
        }
        if keyword:
            clauses.append("(LOWER(g.group_name) LIKE :keyword OR LOWER(g.chat_id) LIKE :keyword)")
        if owner_userid:
            clauses.append("g.owner_userid = :owner_userid")
        if bind_status == "bound":
            clauses.append("p.id IS NOT NULL")
        elif bind_status == "unbound":
            clauses.append("p.id IS NULL")
        where = f"WHERE {' AND '.join(clauses)}"
        base = f"""
            FROM wecom_group_chat_snapshots g
            LEFT JOIN automation_group_ops_plan_groups pg
              ON pg.chat_id = g.chat_id
             AND pg.status = 'active'
             {join_extra}
            LEFT JOIN automation_group_ops_plans p
              ON p.id = pg.plan_id
             AND p.archived_at IS NULL
        """
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    text(
                        f"""
                        SELECT
                            g.chat_id, g.group_name, g.owner_userid, g.owner_name,
                            g.internal_member_count, g.external_member_count,
                            g.synced_at, g.status,
                            p.id AS bound_plan_id, p.plan_name AS plan_name
                        {base}
                        {where}
                        ORDER BY g.group_name ASC, g.chat_id ASC
                        LIMIT :limit OFFSET :offset
                        """
                    ),
                    params,
                ).fetchall()
                total = conn.execute(
                    text(f"SELECT COUNT(*) AS total {base} {where}"),
                    {key: value for key, value in params.items() if key not in {"limit", "offset"}},
                ).scalar_one()
                return [self._row_to_group_asset(_as_mapping(row) or {}) for row in rows], int(total or 0)
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def get_group_asset(self, chat_id: str) -> dict[str, Any] | None:
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT *
                        FROM wecom_group_chat_snapshots
                        WHERE chat_id = :chat_id
                          AND status = 'active'
                        LIMIT 1
                        """
                    ),
                    {"chat_id": clean_text(chat_id)},
                ).fetchone()
                return self._row_to_group_asset(_as_mapping(row)) if row else None
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def upsert_group_snapshots(self, groups: list[dict[str, Any]]) -> int:
        count = 0
        try:
            with self._engine.begin() as conn:
                for group in groups:
                    chat_id = clean_text(group.get("chat_id"))
                    if not chat_id:
                        continue
                    params = {
                        "chat_id": chat_id,
                        "group_name": clean_text(group.get("group_name") or chat_id),
                        "owner_userid": clean_text(group.get("owner_userid")),
                        "owner_name": clean_text(group.get("owner_name") or group.get("owner_userid")),
                        "internal_member_count": _int(group.get("internal_member_count")),
                        "external_member_count": _int(group.get("external_member_count")),
                        "status": clean_text(group.get("status") or "active"),
                    }
                    conn.execute(
                        text(
                            """
                            INSERT INTO wecom_group_chat_snapshots (
                                chat_id, group_name, owner_userid, owner_name,
                                internal_member_count, external_member_count,
                                synced_at, status
                            )
                            VALUES (
                                :chat_id, :group_name, :owner_userid, :owner_name,
                                :internal_member_count, :external_member_count,
                                CURRENT_TIMESTAMP, :status
                            )
                            ON CONFLICT(chat_id) DO UPDATE SET
                                group_name = excluded.group_name,
                                owner_userid = excluded.owner_userid,
                                owner_name = excluded.owner_name,
                                internal_member_count = excluded.internal_member_count,
                                external_member_count = excluded.external_member_count,
                                synced_at = CURRENT_TIMESTAMP,
                                status = excluded.status
                            """
                        ),
                        params,
                    )
                    count += 1
                return count
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def list_owners(self) -> list[dict[str, Any]]:
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT
                            owner_userid AS userid,
                            COALESCE(NULLIF(MAX(owner_name), ''), owner_userid) AS name,
                            COUNT(*) AS group_count
                        FROM wecom_group_chat_snapshots
                        WHERE status = 'active'
                          AND owner_userid <> ''
                        GROUP BY owner_userid
                        ORDER BY owner_userid ASC
                        """
                    )
                ).fetchall()
                return [
                    {
                        "userid": clean_text((_as_mapping(row) or {}).get("userid")),
                        "name": clean_text((_as_mapping(row) or {}).get("name") or (_as_mapping(row) or {}).get("userid")),
                        "group_count": _int((_as_mapping(row) or {}).get("group_count")),
                    }
                    for row in rows
                ]
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def list_nodes(self, plan_id: int) -> list[dict[str, Any]]:
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT *
                        FROM automation_group_ops_plan_nodes
                        WHERE plan_id = :plan_id
                          AND status <> 'deleted'
                        ORDER BY day_index ASC, sort_order ASC, id ASC
                        """
                    ),
                    {"plan_id": int(plan_id)},
                ).fetchall()
                return [self._row_to_node(_as_mapping(row) or {}) for row in rows]
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def create_node(self, plan_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            with self._engine.begin() as conn:
                row = conn.execute(
                    text(
                        """
                        INSERT INTO automation_group_ops_plan_nodes (
                            plan_id, day_index, trigger_time_label, action_title,
                            text_content, attachments_json, sort_order, status
                        )
                        VALUES (
                            :plan_id, :day_index, :trigger_time_label, :action_title,
                            :text_content, :attachments_json, :sort_order, :status
                        )
                        RETURNING id
                        """
                    ),
                    {"plan_id": int(plan_id), **self._node_params(payload)},
                ).fetchone()
                node_id = int((_as_mapping(row) or {}).get("id") or 0)
                return self._get_node_sql(conn, node_id) or {}
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def update_node(self, plan_id: int, node_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            with self._engine.begin() as conn:
                result = conn.execute(
                    text(
                        """
                        UPDATE automation_group_ops_plan_nodes
                        SET day_index = :day_index,
                            trigger_time_label = :trigger_time_label,
                            action_title = :action_title,
                            text_content = :text_content,
                            attachments_json = :attachments_json,
                            sort_order = :sort_order,
                            status = :status,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :node_id
                          AND plan_id = :plan_id
                        """
                    ),
                    {"node_id": int(node_id), "plan_id": int(plan_id), **self._node_params(payload)},
                )
                if not result.rowcount:
                    raise NotFoundError("group ops node not found")
                return self._get_node_sql(conn, int(node_id)) or {}
        except NotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def delete_node(self, plan_id: int, node_id: int) -> bool:
        try:
            with self._engine.begin() as conn:
                result = conn.execute(
                    text(
                        """
                        UPDATE automation_group_ops_plan_nodes
                        SET status = 'deleted', updated_at = CURRENT_TIMESTAMP
                        WHERE id = :node_id
                          AND plan_id = :plan_id
                          AND status <> 'deleted'
                        """
                    ),
                    {"node_id": int(node_id), "plan_id": int(plan_id)},
                )
                return bool(result.rowcount)
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def regenerate_webhook(self, plan_id: int) -> dict[str, Any]:
        try:
            with self._engine.begin() as conn:
                plan = self._get_plan_sql(conn, int(plan_id))
                if not plan:
                    raise NotFoundError("group ops plan not found")
                webhook_key = clean_text(plan.get("webhook_key")) or generate_webhook_key(plan["plan_name"])
                plaintext_token = generate_webhook_token()
                conn.execute(
                    text(
                        """
                        UPDATE automation_group_ops_plans
                        SET webhook_key = :webhook_key,
                            webhook_token_hash = :webhook_token_hash,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :plan_id
                        """
                    ),
                    {
                        "plan_id": int(plan_id),
                        "webhook_key": webhook_key,
                        "webhook_token_hash": hash_webhook_token(plaintext_token),
                    },
                )
                result = self._get_plan_sql(conn, int(plan_id)) or {}
                result["plaintext_token"] = plaintext_token
                return result
        except NotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def find_webhook_event(self, plan_id: int, idempotency_key: str) -> dict[str, Any] | None:
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT *
                        FROM automation_group_ops_webhook_events
                        WHERE plan_id = :plan_id
                          AND idempotency_key = :idempotency_key
                        LIMIT 1
                        """
                    ),
                    {"plan_id": int(plan_id), "idempotency_key": clean_text(idempotency_key)},
                ).fetchone()
                return self._row_to_event(_as_mapping(row)) if row else None
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def create_webhook_event(self, plan_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            with self._engine.begin() as conn:
                row = conn.execute(
                    text(
                        """
                        INSERT INTO automation_group_ops_webhook_events (
                            plan_id, idempotency_key, request_payload,
                            normalized_content_payload, scheduled_at, status,
                            broadcast_job_ids_json, error_message
                        )
                        VALUES (
                            :plan_id, :idempotency_key, :request_payload,
                            :normalized_content_payload, :scheduled_at, :status,
                            :broadcast_job_ids_json, :error_message
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "plan_id": int(plan_id),
                        "idempotency_key": clean_text(payload.get("idempotency_key")),
                        "request_payload": _json_dumps(payload.get("request_payload") or {}),
                        "normalized_content_payload": _json_dumps(payload.get("normalized_content_payload") or {}),
                        "scheduled_at": clean_text(payload.get("scheduled_at")) or None,
                        "status": clean_text(payload.get("status") or "accepted"),
                        "broadcast_job_ids_json": _json_dumps(list(payload.get("broadcast_job_ids") or [])),
                        "error_message": clean_text(payload.get("error_message")),
                    },
                ).fetchone()
                event_id = int((_as_mapping(row) or {}).get("id") or 0)
                return self._get_event_sql(conn, event_id) or {}
        except IntegrityError as exc:
            raise ContractError("webhook idempotency_key already exists for this plan") from exc
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def update_webhook_event(self, event_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if "status" in payload:
            updates["status"] = clean_text(payload.get("status"))
        if "error_message" in payload:
            updates["error_message"] = clean_text(payload.get("error_message"))
        if "broadcast_job_ids" in payload:
            updates["broadcast_job_ids_json"] = _json_dumps(list(payload.get("broadcast_job_ids") or []))
        if not updates:
            current = self._get_event_public(int(event_id))
            if not current:
                raise NotFoundError("group ops webhook event not found")
            return current
        set_clause = ", ".join(f"{key} = :{key}" for key in updates)
        try:
            with self._engine.begin() as conn:
                result = conn.execute(
                    text(f"UPDATE automation_group_ops_webhook_events SET {set_clause} WHERE id = :event_id"),
                    {**updates, "event_id": int(event_id)},
                )
                if not result.rowcount:
                    raise NotFoundError("group ops webhook event not found")
                return self._get_event_sql(conn, int(event_id)) or {}
        except NotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops repository unavailable: {exc}") from exc

    def _get_plan_sql(self, conn: Any, plan_id: int) -> dict[str, Any] | None:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM automation_group_ops_plans
                WHERE id = :plan_id
                  AND archived_at IS NULL
                LIMIT 1
                """
            ),
            {"plan_id": int(plan_id)},
        ).fetchone()
        return self._row_to_plan(conn, _as_mapping(row)) if row else None

    def _get_plan_group_sql(self, conn: Any, binding_id: int) -> dict[str, Any] | None:
        row = conn.execute(
            text("SELECT * FROM automation_group_ops_plan_groups WHERE id = :binding_id LIMIT 1"),
            {"binding_id": int(binding_id)},
        ).fetchone()
        return self._row_to_plan_group(_as_mapping(row)) if row else None

    def _get_node_sql(self, conn: Any, node_id: int) -> dict[str, Any] | None:
        row = conn.execute(
            text("SELECT * FROM automation_group_ops_plan_nodes WHERE id = :node_id LIMIT 1"),
            {"node_id": int(node_id)},
        ).fetchone()
        return self._row_to_node(_as_mapping(row)) if row else None

    def _get_event_sql(self, conn: Any, event_id: int) -> dict[str, Any] | None:
        row = conn.execute(
            text("SELECT * FROM automation_group_ops_webhook_events WHERE id = :event_id LIMIT 1"),
            {"event_id": int(event_id)},
        ).fetchone()
        return self._row_to_event(_as_mapping(row)) if row else None

    def _get_event_public(self, event_id: int) -> dict[str, Any] | None:
        with self._engine.connect() as conn:
            return self._get_event_sql(conn, int(event_id))

    def _owner_name_for_userid(self, conn: Any, owner_userid: str) -> str:
        if not owner_userid:
            return ""
        row = conn.execute(
            text(
                """
                SELECT owner_name
                FROM wecom_group_chat_snapshots
                WHERE owner_userid = :owner_userid
                  AND owner_name <> ''
                ORDER BY synced_at DESC, chat_id ASC
                LIMIT 1
                """
            ),
            {"owner_userid": owner_userid},
        ).fetchone()
        return clean_text((_as_mapping(row) or {}).get("owner_name")) if row else ""

    def _row_to_plan(self, conn: Any, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        owner_userid = clean_text(row.get("owner_userid"))
        return {
            "id": _int(row.get("id")),
            "plan_code": clean_text(row.get("plan_code")),
            "plan_name": clean_text(row.get("plan_name")),
            "plan_type": clean_text(row.get("plan_type")),
            "owner_userid": owner_userid,
            "owner_name": self._owner_name_for_userid(conn, owner_userid),
            "status": clean_text(row.get("status")),
            "webhook_key": clean_text(row.get("webhook_key")),
            "webhook_token_hash": clean_text(row.get("webhook_token_hash")),
            "created_by": clean_text(row.get("created_by")),
            "updated_by": clean_text(row.get("updated_by")),
            "created_at": _iso(row.get("created_at")),
            "updated_at": _iso(row.get("updated_at")),
            "archived_at": _iso(row.get("archived_at")),
        }

    def _row_to_plan_group(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        return {
            "id": _int(row.get("id")),
            "plan_id": _int(row.get("plan_id")),
            "chat_id": clean_text(row.get("chat_id")),
            "group_name_snapshot": clean_text(row.get("group_name_snapshot")),
            "owner_userid_snapshot": clean_text(row.get("owner_userid_snapshot")),
            "internal_member_count_snapshot": _int(row.get("internal_member_count_snapshot")),
            "external_member_count_snapshot": _int(row.get("external_member_count_snapshot")),
            "status": clean_text(row.get("status")),
            "created_at": _iso(row.get("created_at")),
            "removed_at": _iso(row.get("removed_at")),
        }

    def _row_to_group_asset(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        bound_plan_id = _int(row.get("bound_plan_id"))
        return {
            "chat_id": clean_text(row.get("chat_id")),
            "group_name": clean_text(row.get("group_name")),
            "owner_userid": clean_text(row.get("owner_userid")),
            "owner_name": clean_text(row.get("owner_name")),
            "internal_member_count": _int(row.get("internal_member_count")),
            "external_member_count": _int(row.get("external_member_count")),
            "synced_at": _iso(row.get("synced_at")),
            "status": clean_text(row.get("status")),
            "bound_plan_id": bound_plan_id,
            "plan_name": clean_text(row.get("plan_name")) if bound_plan_id else "",
            "bind_status": "bound" if bound_plan_id else "unbound",
        }

    def _row_to_node(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        return {
            "id": _int(row.get("id")),
            "plan_id": _int(row.get("plan_id")),
            "day_index": _int(row.get("day_index")),
            "trigger_time_label": clean_text(row.get("trigger_time_label")),
            "action_title": clean_text(row.get("action_title")),
            "text_content": clean_text(row.get("text_content")),
            "attachments": _json_loads(row.get("attachments_json"), []),
            "sort_order": _int(row.get("sort_order")),
            "status": clean_text(row.get("status")),
            "created_at": _iso(row.get("created_at")),
            "updated_at": _iso(row.get("updated_at")),
        }

    def _row_to_event(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        return {
            "id": _int(row.get("id")),
            "plan_id": _int(row.get("plan_id")),
            "idempotency_key": clean_text(row.get("idempotency_key")),
            "request_payload": _json_loads(row.get("request_payload"), {}),
            "normalized_content_payload": _json_loads(row.get("normalized_content_payload"), {}),
            "scheduled_at": _iso(row.get("scheduled_at")),
            "status": clean_text(row.get("status")),
            "broadcast_job_ids": _json_loads(row.get("broadcast_job_ids_json"), []),
            "error_message": clean_text(row.get("error_message")),
            "created_at": _iso(row.get("created_at")),
        }

    def _group_binding_params(self, *, group: dict[str, Any], binding_id: int | None = None) -> dict[str, Any]:
        params = {
            "group_name": clean_text(group.get("group_name")),
            "owner_userid": clean_text(group.get("owner_userid")),
            "internal_count": _int(group.get("internal_member_count")),
            "external_count": _int(group.get("external_member_count")),
        }
        if binding_id is not None:
            params["binding_id"] = int(binding_id)
        return params

    def _node_params(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "day_index": _int(payload.get("day_index")) or 1,
            "trigger_time_label": clean_text(payload.get("trigger_time_label")),
            "action_title": clean_text(payload.get("action_title")),
            "text_content": clean_text(payload.get("text_content")),
            "attachments_json": _json_dumps(list(payload.get("attachments") or [])),
            "sort_order": _int(payload.get("sort_order")),
            "status": clean_text(payload.get("status") or "active"),
        }
