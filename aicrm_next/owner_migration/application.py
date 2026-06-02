from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from aicrm_next.channel_entry.wecom_adapter import (
    WeComApiError,
    ProductionWeComAdapter,
    missing_wecom_config,
)
from aicrm_next.shared.runtime import production_data_ready

from .repo import FixtureOwnerMigrationRepository, PostgresOwnerMigrationRepository


def clean_text(value: Any) -> str:
    return str(value or "").strip()


@dataclass(frozen=True)
class OwnerMigrationCommand:
    source_owner_userid: str
    target_owner_userid: str
    operator: str = ""
    transfer_success_msg: str = ""
    batch_size: int = 100
    perform_wecom_transfer: bool = True
    execute: bool = False
    confirm: bool = False


class OwnerMigrationRepository(Protocol):
    source_status: str

    def preview_owner_migration(self, *, source_owner_userid: str, target_owner_userid: str) -> dict[str, Any]: ...
    def execute_owner_migration(
        self,
        *,
        source_owner_userid: str,
        target_owner_userid: str,
        operator: str,
        external_userids: list[str] | None = None,
    ) -> dict[str, Any]: ...


class OwnerMigrationService:
    def __init__(self, repo: OwnerMigrationRepository) -> None:
        self._repo = repo

    def run(self, command: OwnerMigrationCommand) -> dict[str, Any]:
        source = clean_text(command.source_owner_userid)
        target = clean_text(command.target_owner_userid)
        operator = clean_text(command.operator) or "crm_console"
        if not source:
            return _error("source_owner_userid_required", "source_owner_userid is required")
        if not target:
            return _error("target_owner_userid_required", "target_owner_userid is required")
        if source == target:
            return _error("same_owner_userid", "source and target owner_userid must be different")
        if command.execute:
            if not command.confirm:
                return _error("confirm_required", "confirm is required before executing owner migration")
            preview = self._repo.preview_owner_migration(
                source_owner_userid=source,
                target_owner_userid=target,
            )
            candidates = [clean_text(item) for item in preview.get("all_external_userids", []) if clean_text(item)]
            transfer = _transfer_customers(
                source_owner_userid=source,
                target_owner_userid=target,
                external_userids=candidates,
                transfer_success_msg=clean_text(command.transfer_success_msg),
                batch_size=max(1, min(int(command.batch_size or 100), 100)),
                enabled=bool(command.perform_wecom_transfer),
            )
            if not transfer.get("ok"):
                return {
                    "ok": False,
                    "mode": "execute",
                    "source_owner_userid": source,
                    "target_owner_userid": target,
                    "operator": operator,
                    **preview,
                    "wecom_transfer": transfer,
                    "error_code": transfer.get("error_code") or "wecom_transfer_failed",
                    "error": transfer.get("error") or "WeCom transfer failed",
                    "status_code": 502,
                }
            success_external_userids = list(transfer.get("success_external_userids") or [])
            result = self._repo.execute_owner_migration(
                source_owner_userid=source,
                target_owner_userid=target,
                operator=operator,
                external_userids=success_external_userids if command.perform_wecom_transfer else None,
            )
            result["wecom_transfer"] = transfer
        else:
            result = self._repo.preview_owner_migration(
                source_owner_userid=source,
                target_owner_userid=target,
            )
        return {
            "ok": True,
            "mode": "execute" if command.execute else "preview",
            "source_owner_userid": source,
            "target_owner_userid": target,
            "operator": operator,
            "wecom_diagnostics": _wecom_transfer_diagnostics(),
            **result,
        }


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error_code": code, "error": message, "status_code": 400}


def build_owner_migration_service() -> OwnerMigrationService:
    repo: OwnerMigrationRepository
    if production_data_ready():
        repo = PostgresOwnerMigrationRepository()
    else:
        repo = FixtureOwnerMigrationRepository()
    return OwnerMigrationService(repo)


def _transfer_customers(
    *,
    source_owner_userid: str,
    target_owner_userid: str,
    external_userids: list[str],
    transfer_success_msg: str,
    batch_size: int,
    enabled: bool,
) -> dict[str, Any]:
    if not enabled:
        return {
            "ok": True,
            "enabled": False,
            "success_external_userids": list(external_userids),
            "failed_customers": [],
            "batches": [],
        }
    if not external_userids:
        return {"ok": True, "enabled": True, "success_external_userids": [], "failed_customers": [], "batches": []}
    missing = missing_wecom_config()
    if missing:
        return {
            "ok": False,
            "enabled": True,
            "error_code": "missing_wecom_config",
            "error": "WeCom transfer config is missing",
            "missing_config": missing,
            "success_external_userids": [],
            "failed_customers": [],
            "batches": [],
        }
    adapter = ProductionWeComAdapter()
    success_external_userids: list[str] = []
    failed_customers: list[dict[str, Any]] = []
    batches: list[dict[str, Any]] = []
    for batch_index, start in enumerate(range(0, len(external_userids), batch_size), start=1):
        batch = external_userids[start : start + batch_size]
        payload: dict[str, Any] = {
            "handover_userid": source_owner_userid,
            "takeover_userid": target_owner_userid,
            "external_userid": batch,
        }
        if transfer_success_msg:
            payload["transfer_success_msg"] = transfer_success_msg
        try:
            response = adapter.transfer_customer(payload)
        except WeComApiError as exc:
            return {
                "ok": False,
                "enabled": True,
                "error_code": "wecom_api_error",
                "error": exc.message,
                "payload": exc.payload,
                "success_external_userids": success_external_userids,
                "failed_customers": failed_customers,
                "batches": batches,
            }
        customer_results = list(response.get("customer") or [])
        reported_external_userids = {clean_text(item.get("external_userid")) for item in customer_results}
        batch_success = [
            clean_text(item.get("external_userid"))
            for item in customer_results
            if int(item.get("errcode") or 0) == 0 and clean_text(item.get("external_userid"))
        ]
        batch_failed = [
            {"external_userid": clean_text(item.get("external_userid")), "errcode": int(item.get("errcode") or 0)}
            for item in customer_results
            if int(item.get("errcode") or 0) != 0
        ]
        batch_failed.extend(
            {"external_userid": external_userid, "errcode": -1, "errmsg": "missing_transfer_result"}
            for external_userid in batch
            if external_userid not in reported_external_userids
        )
        success_external_userids.extend(batch_success)
        failed_customers.extend(batch_failed)
        batches.append(
            {
                "batch_index": batch_index,
                "requested_count": len(batch),
                "success_count": len(batch_success),
                "failed_count": len(batch_failed),
                "errcode": int(response.get("errcode") or 0),
                "errmsg": clean_text(response.get("errmsg")),
            }
        )
    return {
        "ok": True,
        "enabled": True,
        "requested_count": len(external_userids),
        "success_count": len(success_external_userids),
        "failed_count": len(failed_customers),
        "success_external_userids": success_external_userids,
        "failed_customers": failed_customers,
        "batches": batches,
    }


def query_wecom_transfer_result(*, source_owner_userid: str, target_owner_userid: str, cursor: str = "") -> dict[str, Any]:
    source = clean_text(source_owner_userid)
    target = clean_text(target_owner_userid)
    if not source:
        return _error("source_owner_userid_required", "source_owner_userid is required")
    if not target:
        return _error("target_owner_userid_required", "target_owner_userid is required")
    payload: dict[str, Any] = {"handover_userid": source, "takeover_userid": target}
    if clean_text(cursor):
        payload["cursor"] = clean_text(cursor)
    missing = missing_wecom_config()
    if missing:
        return {
            "ok": False,
            "error_code": "missing_wecom_config",
            "error": "WeCom transfer config is missing",
            "missing_config": missing,
            "status_code": 502,
        }
    try:
        result = ProductionWeComAdapter().transfer_result(payload)
    except WeComApiError as exc:
        return {
            "ok": False,
            "error_code": "wecom_api_error",
            "error": exc.message,
            "payload": exc.payload,
            "status_code": 502,
        }
    return {"ok": True, "source_owner_userid": source, "target_owner_userid": target, **result}


def _wecom_transfer_diagnostics() -> dict[str, Any]:
    missing = missing_wecom_config()
    return {
        "can_transfer_customer": not missing,
        "missing_config": missing,
        "real_wecom_adapter_reason": "missing_wecom_config" if missing else "enabled_by_owner_migration_confirmation",
    }
