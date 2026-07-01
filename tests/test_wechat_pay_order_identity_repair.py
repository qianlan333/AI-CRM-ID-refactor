from __future__ import annotations

from pathlib import Path
from typing import Any

from aicrm_next.commerce.order_identity_repair import repair_missing_order_identities


class _Cursor:
    def __init__(self, rows: list[dict[str, Any]] | None = None, row: dict[str, Any] | None = None) -> None:
        self._rows = rows or []
        self._row = row

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._row


class _RepairConn:
    def __init__(self, *, identity: dict[str, Any] | None = None, unresolved_attempt_after: int = 1) -> None:
        self.identity = identity
        self.unresolved_attempt_after = unresolved_attempt_after
        self.queries: list[tuple[str, tuple[Any, ...]]] = []
        self.committed = False
        self.rolled_back = False

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> _Cursor:
        self.queries.append((query, params))
        if "FROM wechat_pay_orders o" in query and "LEFT JOIN wechat_pay_order_identity_repair" in query:
            return _Cursor(
                rows=[
                    {
                        "id": 188,
                        "out_trade_no": "WXP260630074008B968C34438C0",
                        "product_code": "SOAK-QTR",
                        "product_name": "浸泡学习营·季度",
                        "unionid": "union_paid_001",
                        "payer_openid": "openid_paid_001",
                        "mobile_snapshot": "18811725941",
                        "external_userid": "",
                        "userid_snapshot": "",
                        "paid_at": "2026-06-30 15:40:16+08",
                        "repair_attempt_count": self.unresolved_attempt_after - 1,
                        "repair_status": "retryable" if self.unresolved_attempt_after > 1 else "pending",
                    }
                ]
            )
        if "FROM wecom_external_contact_identity_map" in query:
            return _Cursor(row=self.identity)
        if "FROM people p" in query:
            return _Cursor(row=None)
        if "RETURNING status, attempt_count" in query:
            status = "exhausted" if self.unresolved_attempt_after >= 3 else "retryable"
            return _Cursor(row={"status": status, "attempt_count": self.unresolved_attempt_after})
        return _Cursor(row=None)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def test_order_identity_repair_resolves_missing_external_userid_by_unionid() -> None:
    conn = _RepairConn(identity={"external_userid": "wmbNXyCwAA_syOI8dRmuF4-1kciWS1dQ", "owner_userid": "HuangYouCan"})

    result = repair_missing_order_identities(conn=conn, limit=10, max_attempts=3)

    assert result["repaired_count"] == 1
    assert result["retryable_count"] == 0
    assert result["items"][0]["matched_by"] == "unionid"
    assert result["items"][0]["external_userid"] == "wmbNXyCwAA_syOI8dRmuF4-1kciWS1dQ"
    assert conn.committed is True
    order_updates = [item for item in conn.queries if "UPDATE wechat_pay_orders" in item[0]]
    assert order_updates
    assert order_updates[0][1][0] == "wmbNXyCwAA_syOI8dRmuF4-1kciWS1dQ"
    assert order_updates[0][1][1] == "HuangYouCan"


def test_order_identity_repair_exhausts_after_third_unresolved_attempt() -> None:
    conn = _RepairConn(identity=None, unresolved_attempt_after=3)

    result = repair_missing_order_identities(conn=conn, limit=10, max_attempts=3)

    assert result["repaired_count"] == 0
    assert result["exhausted_count"] == 1
    assert result["items"][0]["status"] == "exhausted"
    assert result["items"][0]["attempt_count_after"] == 3
    assert conn.committed is True


def test_order_identity_repair_route_is_cron_or_action_token_protected() -> None:
    source = Path("aicrm_next/admin_jobs/routes.py").read_text(encoding="utf-8")

    assert '@router.post("/api/admin/jobs/order-identity-repair/run")' in source
    route_block = source.split('@router.post("/api/admin/jobs/order-identity-repair/run")', 1)[1].split('@router.post("/api/admin/broadcast-jobs/{job_id}/approve")', 1)[0]
    assert "_cron_or_action_token_error(request, payload)" in route_block
    assert "repair_missing_order_identities(" in route_block
    assert "normalized_int(payload.get(\"limit\"), default=100, minimum=1, maximum=1000)" in route_block
    assert "normalized_int(payload.get(\"max_attempts\"), default=3, minimum=1, maximum=10)" in route_block
    assert "dry_run=normalized_bool(payload.get(\"dry_run\"))" in route_block


def test_order_identity_repair_migration_tracks_attempts_and_due_index() -> None:
    source = Path("migrations/versions/0062_wechat_pay_order_identity_repair.py").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS wechat_pay_order_identity_repair" in source
    assert "attempt_count INTEGER NOT NULL DEFAULT 0" in source
    assert "max_attempts INTEGER NOT NULL DEFAULT 3" in source
    assert "idx_wechat_pay_order_identity_repair_due" in source
    assert "idx_wechat_pay_orders_missing_identity_paid" in source
