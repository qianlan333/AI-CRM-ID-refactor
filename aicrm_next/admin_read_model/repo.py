from __future__ import annotations

import os
from typing import Any, Protocol

from aicrm_next.shared.runtime import database_mode, production_data_ready, runtime_health_state
from aicrm_next.shared.repository_provider import assert_repository_allowed

from .dto import AdminReadDiagnostics
from .errors import AdminReadModelError


class AdminReadRepository(Protocol):
    source_status: str

    @property
    def is_production(self) -> bool: ...

    def rows(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]: ...

    def one(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any]: ...

    def count(self, table: str) -> int: ...

    def runtime_health(self) -> dict[str, Any]: ...

    def diagnostics(self) -> AdminReadDiagnostics: ...


def _database_url() -> str:
    return str(os.getenv("DATABASE_URL", "") or "").strip()


class PostgresAdminReadRepository:
    source_status = "production_postgres"

    @property
    def is_production(self) -> bool:
        return True

    def rows(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ModuleNotFoundError as exc:
            raise AdminReadModelError("psycopg is required for production admin read model") from exc
        try:
            with psycopg.connect(_database_url(), row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    return [dict(row) for row in cur.fetchall()]
        except Exception as exc:
            raise AdminReadModelError(str(exc)) from exc

    def one(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
        rows = self.rows(query, params)
        return rows[0] if rows else {}

    def count(self, table: str) -> int:
        row = self.one(
            """
            SELECT CASE WHEN to_regclass(%s) IS NULL THEN 0
                        ELSE (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %I', %s), false, true, '')))[1]::text::int
                   END AS count
            """,
            (table, table),
        )
        return int(row.get("count") or 0)

    def runtime_health(self) -> dict[str, Any]:
        return runtime_health_state()

    def diagnostics(self) -> AdminReadDiagnostics:
        return AdminReadDiagnostics(source_status=self.source_status, details={"database_mode": database_mode()})


class LocalContractAdminReadRepository:
    source_status = "local_contract_probe"

    @property
    def is_production(self) -> bool:
        return False

    def rows(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return []

    def one(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
        return {}

    def count(self, table: str) -> int:
        return 0

    def runtime_health(self) -> dict[str, Any]:
        return runtime_health_state()

    def diagnostics(self) -> AdminReadDiagnostics:
        return AdminReadDiagnostics(source_status=self.source_status, details={"database_mode": database_mode()})


def build_admin_read_repository() -> AdminReadRepository:
    if production_data_ready():
        return assert_repository_allowed(PostgresAdminReadRepository(), capability_owner="admin_read_model")
    return assert_repository_allowed(LocalContractAdminReadRepository(), capability_owner="admin_read_model")
