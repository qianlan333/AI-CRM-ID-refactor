from __future__ import annotations

import json
import os
from typing import Any


def _table_exists(conn, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (table_name,))
        row = cur.fetchone()
        return bool(row and row.get("exists"))


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = ANY (current_schemas(FALSE))
                  AND table_name = %s
                  AND column_name = %s
            ) AS exists
            """,
            (table_name, column_name),
        )
        row = cur.fetchone()
        return bool(row and row.get("exists"))


def _row_count(conn, query: str, params: tuple[Any, ...]) -> int:
    with conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return int((row or {}).get("count") or 0)


def _returning_external_userids(conn, query: str, params: tuple[Any, ...]) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(query, params)
        return [str(row.get("external_userid") or "").strip() for row in cur.fetchall()]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _external_scope_clause(external_userids: list[str] | None) -> tuple[str, tuple[Any, ...]]:
    if external_userids is None:
        return "", ()
    values = [str(item or "").strip() for item in external_userids if str(item or "").strip()]
    if not values:
        return " AND FALSE", ()
    return " AND external_userid = ANY(%s::text[])", (values,)


class FixtureOwnerMigrationRepository:
    source_status = "local_contract_probe"

    def preview_owner_migration(self, *, source_owner_userid: str, target_owner_userid: str) -> dict[str, Any]:
        return {
            "source_status": self.source_status,
            "candidate_count": 0,
            "all_external_userids": [],
            "sample_external_userids": [],
            "surface_counts": {},
            "pending_review": {},
            "notes": ["DATABASE_URL is not PostgreSQL; owner migration is available only against production data."],
        }

    def execute_owner_migration(
        self,
        *,
        source_owner_userid: str,
        target_owner_userid: str,
        operator: str,
        external_userids: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            **self.preview_owner_migration(
                source_owner_userid=source_owner_userid,
                target_owner_userid=target_owner_userid,
            ),
            "update_counts": {},
            "executed": False,
        }


class PostgresOwnerMigrationRepository:
    source_status = "production_postgres"

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(os.getenv("DATABASE_URL", ""), row_factory=dict_row)

    def preview_owner_migration(self, *, source_owner_userid: str, target_owner_userid: str) -> dict[str, Any]:
        with self._connect() as conn:
            candidates = self._candidate_rows(conn, source_owner_userid)
            return {
                "source_status": self.source_status,
                "candidate_count": len(candidates),
                "all_external_userids": [row["external_userid"] for row in candidates],
                "sample_external_userids": [row["external_userid"] for row in candidates[:20]],
                "surface_counts": self._surface_counts(conn, source_owner_userid),
                "pending_review": self._pending_review_counts(conn, source_owner_userid),
                "notes": [
                    "Execution calls WeCom customer transfer first, then updates CRM rows for successful external_userids.",
                    "Pending jobs and historical messages are reported for review but are not rewritten automatically.",
                ],
            }

    def execute_owner_migration(
        self,
        *,
        source_owner_userid: str,
        target_owner_userid: str,
        operator: str,
        external_userids: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            before = self.preview_owner_migration(
                source_owner_userid=source_owner_userid,
                target_owner_userid=target_owner_userid,
            )
            update_counts: dict[str, int] = {}
            touched: list[str] = []
            scope_clause, scope_params = _external_scope_clause(external_userids)
            if _table_exists(conn, "contacts"):
                values = _returning_external_userids(
                    conn,
                    f"""
                    UPDATE contacts
                    SET owner_userid = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE owner_userid = %s AND COALESCE(external_userid, '') <> ''
                    {scope_clause}
                    RETURNING external_userid
                    """,
                    (target_owner_userid, source_owner_userid, *scope_params),
                )
                update_counts["contacts"] = len(values)
                touched.extend(values)
            if _table_exists(conn, "external_contact_bindings"):
                values = _returning_external_userids(
                    conn,
                    f"""
                    UPDATE external_contact_bindings
                    SET last_owner_userid = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE last_owner_userid = %s AND COALESCE(external_userid, '') <> ''
                    {scope_clause}
                    RETURNING external_userid
                    """,
                    (target_owner_userid, source_owner_userid, *scope_params),
                )
                update_counts["external_contact_bindings"] = len(values)
                touched.extend(values)
            if _table_exists(conn, "user_ops_lead_pool_current"):
                values = _returning_external_userids(
                    conn,
                    f"""
                    UPDATE user_ops_lead_pool_current
                    SET owner_userid = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE owner_userid = %s AND COALESCE(external_userid, '') <> ''
                    {scope_clause}
                    RETURNING external_userid
                    """,
                    (target_owner_userid, source_owner_userid, *scope_params),
                )
                update_counts["user_ops_lead_pool_current"] = len(values)
                touched.extend(values)
            if _table_exists(conn, "wecom_external_contact_identity_map"):
                values = _returning_external_userids(
                    conn,
                    f"""
                    UPDATE wecom_external_contact_identity_map
                    SET follow_user_userid = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE follow_user_userid = %s AND COALESCE(external_userid, '') <> ''
                    {scope_clause}
                    RETURNING external_userid
                    """,
                    (target_owner_userid, source_owner_userid, *scope_params),
                )
                update_counts["wecom_external_contact_identity_map"] = len(values)
                touched.extend(values)
            if _table_exists(conn, "wecom_external_contact_follow_users"):
                inserted = _returning_external_userids(
                    conn,
                    f"""
                    WITH source_rows AS (
                        SELECT *
                        FROM wecom_external_contact_follow_users
                        WHERE user_id = %s
                          AND COALESCE(external_userid, '') <> ''
                          AND COALESCE(relation_status, 'active') = 'active'
                          {scope_clause}
                    )
                    INSERT INTO wecom_external_contact_follow_users (
                        corp_id, external_userid, user_id, relation_status, is_primary,
                        remark, description, add_way, state, oper_userid, createtime,
                        raw_follow_user, first_seen_at, last_seen_at, created_at, updated_at
                    )
                    SELECT
                        corp_id, external_userid, %s, 'active', TRUE,
                        remark, description, add_way, state, oper_userid, createtime,
                        raw_follow_user, first_seen_at, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    FROM source_rows
                    ON CONFLICT (corp_id, external_userid, user_id) DO UPDATE SET
                        relation_status = 'active',
                        is_primary = TRUE,
                        updated_at = CURRENT_TIMESTAMP,
                        last_seen_at = CURRENT_TIMESTAMP
                    RETURNING external_userid
                    """,
                    (source_owner_userid, *scope_params, target_owner_userid),
                )
                closed = _returning_external_userids(
                    conn,
                    f"""
                    UPDATE wecom_external_contact_follow_users
                    SET relation_status = 'transferred', is_primary = FALSE, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s
                      AND COALESCE(external_userid, '') <> ''
                      AND COALESCE(relation_status, 'active') = 'active'
                      {scope_clause}
                    RETURNING external_userid
                    """,
                    (source_owner_userid, *scope_params),
                )
                update_counts["wecom_external_contact_follow_users_target_active"] = len(inserted)
                update_counts["wecom_external_contact_follow_users_source_transferred"] = len(closed)
                touched.extend(inserted)
                touched.extend(closed)
            if _table_exists(conn, "customer_list_index_next"):
                values = _returning_external_userids(
                    conn,
                    f"""
                    UPDATE customer_list_index_next
                    SET owner_userid = %s,
                        owner_display_name = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE owner_userid = %s AND COALESCE(external_userid, '') <> ''
                    {scope_clause}
                    RETURNING external_userid
                    """,
                    (target_owner_userid, target_owner_userid, source_owner_userid, *scope_params),
                )
                update_counts["customer_list_index_next"] = len(values)
                touched.extend(values)
            if _table_exists(conn, "customer_detail_snapshot_next"):
                values = _returning_external_userids(
                    conn,
                    f"""
                    UPDATE customer_detail_snapshot_next
                    SET customer_json = jsonb_set(
                            jsonb_set(customer_json::jsonb, '{{owner_userid}}', to_jsonb(%s::text), TRUE),
                            '{{owner_display_name}}', to_jsonb(%s::text), TRUE
                        )::json,
                        binding_json = jsonb_set(
                            binding_json::jsonb, '{{last_owner_userid}}', to_jsonb(%s::text), TRUE
                        )::json,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE customer_json::jsonb ->> 'owner_userid' = %s
                      AND COALESCE(external_userid, '') <> ''
                      {scope_clause}
                    RETURNING external_userid
                    """,
                    (target_owner_userid, target_owner_userid, target_owner_userid, source_owner_userid, *scope_params),
                )
                update_counts["customer_detail_snapshot_next"] = len(values)
                touched.extend(values)
            touched_external_userids = _unique(touched)
            after = {
                "update_counts": update_counts,
                "touched_count": len(touched_external_userids),
                "sample_external_userids": touched_external_userids[:20],
                "scoped_to_external_userids": external_userids is not None,
            }
            self._insert_audit(
                conn,
                operator=operator,
                source_owner_userid=source_owner_userid,
                target_owner_userid=target_owner_userid,
                before=before,
                after=after,
            )
            conn.commit()
            return {
                **self.preview_owner_migration(
                    source_owner_userid=source_owner_userid,
                    target_owner_userid=target_owner_userid,
                ),
                "executed": True,
                **after,
            }

    def _candidate_rows(self, conn, source_owner_userid: str) -> list[dict[str, Any]]:
        unions: list[str] = []
        params: list[Any] = []
        surfaces = {
            "contacts": "SELECT external_userid, 'contacts' AS source_table FROM contacts WHERE owner_userid = %s AND COALESCE(external_userid, '') <> ''",
            "external_contact_bindings": "SELECT external_userid, 'external_contact_bindings' AS source_table FROM external_contact_bindings WHERE last_owner_userid = %s AND COALESCE(external_userid, '') <> ''",
            "user_ops_lead_pool_current": "SELECT external_userid, 'user_ops_lead_pool_current' AS source_table FROM user_ops_lead_pool_current WHERE owner_userid = %s AND COALESCE(external_userid, '') <> ''",
            "wecom_external_contact_identity_map": "SELECT external_userid, 'wecom_external_contact_identity_map' AS source_table FROM wecom_external_contact_identity_map WHERE follow_user_userid = %s AND COALESCE(external_userid, '') <> ''",
            "wecom_external_contact_follow_users": "SELECT external_userid, 'wecom_external_contact_follow_users' AS source_table FROM wecom_external_contact_follow_users WHERE user_id = %s AND COALESCE(relation_status, 'active') = 'active' AND COALESCE(external_userid, '') <> ''",
            "customer_list_index_next": "SELECT external_userid, 'customer_list_index_next' AS source_table FROM customer_list_index_next WHERE owner_userid = %s AND COALESCE(external_userid, '') <> ''",
            "customer_detail_snapshot_next": "SELECT external_userid, 'customer_detail_snapshot_next' AS source_table FROM customer_detail_snapshot_next WHERE customer_json::jsonb ->> 'owner_userid' = %s AND COALESCE(external_userid, '') <> ''",
        }
        for table_name, query in surfaces.items():
            if _table_exists(conn, table_name):
                unions.append(query)
                params.append(source_owner_userid)
        if not unions:
            return []
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH candidates AS ({' UNION ALL '.join(unions)})
                SELECT external_userid, ARRAY_AGG(DISTINCT source_table ORDER BY source_table) AS source_tables
                FROM candidates
                GROUP BY external_userid
                ORDER BY external_userid ASC
                """,
                tuple(params),
            )
            return [dict(row) for row in cur.fetchall()]

    def _surface_counts(self, conn, source_owner_userid: str) -> dict[str, int]:
        count_queries = {
            "contacts": ("SELECT COUNT(*) AS count FROM contacts WHERE owner_userid = %s", (source_owner_userid,)),
            "external_contact_bindings": (
                "SELECT COUNT(*) AS count FROM external_contact_bindings WHERE last_owner_userid = %s",
                (source_owner_userid,),
            ),
            "user_ops_lead_pool_current": (
                "SELECT COUNT(*) AS count FROM user_ops_lead_pool_current WHERE owner_userid = %s",
                (source_owner_userid,),
            ),
            "wecom_external_contact_identity_map": (
                "SELECT COUNT(*) AS count FROM wecom_external_contact_identity_map WHERE follow_user_userid = %s",
                (source_owner_userid,),
            ),
            "wecom_external_contact_follow_users": (
                "SELECT COUNT(*) AS count FROM wecom_external_contact_follow_users WHERE user_id = %s AND COALESCE(relation_status, 'active') = 'active'",
                (source_owner_userid,),
            ),
            "customer_list_index_next": (
                "SELECT COUNT(*) AS count FROM customer_list_index_next WHERE owner_userid = %s",
                (source_owner_userid,),
            ),
            "customer_detail_snapshot_next": (
                "SELECT COUNT(*) AS count FROM customer_detail_snapshot_next WHERE customer_json::jsonb ->> 'owner_userid' = %s",
                (source_owner_userid,),
            ),
        }
        return {
            table_name: _row_count(conn, query, params)
            for table_name, (query, params) in count_queries.items()
            if _table_exists(conn, table_name)
        }

    def _pending_review_counts(self, conn, source_owner_userid: str) -> dict[str, int]:
        count_queries: dict[str, tuple[str, str, str, tuple[Any, ...]]] = {
            "pending_user_ops_deferred_jobs": (
                "user_ops_deferred_jobs",
                "owner_userid",
                "SELECT COUNT(*) AS count FROM user_ops_deferred_jobs WHERE owner_userid = %s AND status IN ('pending', 'running')",
                (source_owner_userid,),
            ),
            "pending_broadcast_jobs": (
                "broadcast_jobs",
                "owner_userid",
                "SELECT COUNT(*) AS count FROM broadcast_jobs WHERE owner_userid = %s AND status IN ('pending', 'queued', 'running', 'draft')",
                (source_owner_userid,),
            ),
            "pending_outbound_tasks": (
                "outbound_tasks",
                "request_payload",
                "SELECT COUNT(*) AS count FROM outbound_tasks WHERE request_payload LIKE %s AND status IN ('pending', 'created', 'queued')",
                (f"%{source_owner_userid}%",),
            ),
        }
        counts: dict[str, int] = {}
        for key, (table_name, owner_column, query, params) in count_queries.items():
            if not _table_exists(conn, table_name) or not _column_exists(conn, table_name, owner_column):
                continue
            counts[key] = _row_count(conn, query, params)
        return counts

    def _insert_audit(
        self,
        conn,
        *,
        operator: str,
        source_owner_userid: str,
        target_owner_userid: str,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        if not _table_exists(conn, "admin_operation_logs"):
            return
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO admin_operation_logs (
                    operator, action_type, target_type, target_id, before_json, after_json, created_at
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, CURRENT_TIMESTAMP)
                """,
                (
                    operator,
                    "owner_migration_execute",
                    "owner_migration",
                    f"{source_owner_userid}->{target_owner_userid}",
                    json.dumps(before, ensure_ascii=False),
                    json.dumps(after, ensure_ascii=False),
                ),
            )
