from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Callable

from tools.check_data_table_lifecycle import check_data_table_lifecycle

from .dto import DataHealthCheckResult


ROOT = Path(__file__).resolve().parents[2]


def run_all_checks() -> list[DataHealthCheckResult]:
    return [check() for check in _CHECKS]


def run_check(check_id: str) -> DataHealthCheckResult | None:
    for check in _CHECKS:
        result = check()
        if result.check_id == check_id:
            return result
    return None


def _table_lifecycle_manifest_guard() -> DataHealthCheckResult:
    violations = list(_lifecycle_violations())
    return _static_guard_result(
        check_id="table_lifecycle_manifest_guard",
        title="Lifecycle manifest guard",
        violations=violations,
        ok_summary="Lifecycle manifest and table registrations are valid.",
        remediation="Run tools/check_data_table_lifecycle.py and register or fix the reported table entries.",
    )


def _retired_table_runtime_reference_guard() -> DataHealthCheckResult:
    violations = [
        violation
        for violation in _lifecycle_violations()
        if "references retired table" in violation
    ]
    return _static_guard_result(
        check_id="retired_table_runtime_reference_guard",
        title="Retired table runtime reference guard",
        violations=violations,
        ok_summary="No Next runtime SQL references retired lifecycle tables.",
        remediation="Remove the runtime SQL reference or move the table out of retired lifecycle with an approved owner.",
    )


@lru_cache(maxsize=1)
def _lifecycle_violations() -> tuple[str, ...]:
    return tuple(check_data_table_lifecycle(root=ROOT))


def _identity_legacy_column_guard() -> DataHealthCheckResult:
    guard_path = ROOT / "tests" / "test_unionid_final_schema_guard.py"
    source = guard_path.read_text(encoding="utf-8") if guard_path.exists() else ""
    required_tokens = (
        "LEGACY_IDENTITY_COLUMN_NAMES",
        "ALLOWED_FINAL_LEGACY_IDENTITY_COLUMNS",
        "BOUNDARY_PREFIXES",
    )
    missing = [token for token in required_tokens if token not in source]
    return _static_guard_result(
        check_id="identity_legacy_column_guard",
        title="Legacy identity column guard",
        violations=[f"{guard_path.relative_to(ROOT)} missing {token}" for token in missing],
        ok_summary="Final schema guard restricts legacy identity columns to approved identity boundaries.",
        remediation="Restore tests/test_unionid_final_schema_guard.py allowed-boundary assertions.",
    )


def _static_guard_result(
    *,
    check_id: str,
    title: str,
    violations: list[str],
    ok_summary: str,
    remediation: str,
) -> DataHealthCheckResult:
    if violations:
        return DataHealthCheckResult(
            check_id=check_id,
            title=title,
            status="fail",
            severity="red",
            summary=f"{len(violations)} violation(s) found.",
            evidence={"violations": violations[:50], "violation_count": len(violations)},
            remediation=remediation,
        )
    return DataHealthCheckResult(
        check_id=check_id,
        title=title,
        status="ok",
        severity="green",
        summary=ok_summary,
        evidence={"violation_count": 0},
        remediation="",
    )


def _db_backed_placeholder(check_id: str, title: str, source_tables: list[str]) -> DataHealthCheckResult:
    return DataHealthCheckResult(
        check_id=check_id,
        title=title,
        status="not_applicable",
        severity="gray",
        summary="Runtime data check is registered but no production database probe is attached in this PR.",
        evidence={"source_tables": source_tables, "runtime_probe": "not_configured"},
        remediation="Attach a production-safe read repository before turning this into a red/yellow operational check.",
    )


def _unionid_orphan_fact_guard() -> DataHealthCheckResult:
    return _db_backed_placeholder(
        "unionid_orphan_fact_guard",
        "Unionid orphan fact guard",
        ["questionnaire_submissions", "wechat_pay_orders", "broadcast_jobs"],
    )


def _identity_resolution_queue_backlog() -> DataHealthCheckResult:
    return _db_backed_placeholder(
        "identity_resolution_queue_backlog",
        "Identity resolution queue backlog",
        ["crm_user_identity_resolution_queue"],
    )


def _projection_freshness_customer_read_model() -> DataHealthCheckResult:
    return _db_backed_placeholder(
        "projection_freshness_customer_read_model",
        "Customer read model projection freshness",
        ["customer_list_index_next", "customer_detail_snapshot_next"],
    )


def _broadcast_job_blocked_backlog() -> DataHealthCheckResult:
    return _db_backed_placeholder(
        "broadcast_job_blocked_backlog",
        "Broadcast job blocked backlog",
        ["broadcast_jobs", "broadcast_job_events"],
    )


def _external_effect_failed_retryable_backlog() -> DataHealthCheckResult:
    return _db_backed_placeholder(
        "external_effect_failed_retryable_backlog",
        "External effect failed retryable backlog",
        ["external_effect_job", "external_effect_attempt"],
    )


def _questionnaire_submission_without_user_guard() -> DataHealthCheckResult:
    return _db_backed_placeholder(
        "questionnaire_submission_without_user_guard",
        "Questionnaire submissions without identity",
        ["questionnaire_submissions", "crm_user_identity"],
    )


def _payment_order_without_user_guard() -> DataHealthCheckResult:
    return _db_backed_placeholder(
        "payment_order_without_user_guard",
        "Payment orders without identity",
        ["wechat_pay_orders", "alipay_pay_orders", "crm_user_identity"],
    )


_CHECKS: tuple[Callable[[], DataHealthCheckResult], ...] = (
    _identity_legacy_column_guard,
    _table_lifecycle_manifest_guard,
    _retired_table_runtime_reference_guard,
    _unionid_orphan_fact_guard,
    _identity_resolution_queue_backlog,
    _projection_freshness_customer_read_model,
    _broadcast_job_blocked_backlog,
    _external_effect_failed_retryable_backlog,
    _questionnaire_submission_without_user_guard,
    _payment_order_without_user_guard,
)
