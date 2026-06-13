from __future__ import annotations

from typing import Any

from .adapters import webhook_execution_settings
from .service import ExternalEffectService
from .test_receiver import test_execution_only_enabled, test_receiver_enabled

ROUTE_OWNER = "ai_crm_next"
JOB_DISPLAY_FIELDS = [
    "effect_type",
    "status",
    "target_type",
    "target_id",
    "business_type",
    "business_id",
    "trace_id",
    "idempotency_key",
    "attempt_count",
    "last_error_code",
    "last_error_message",
    "created_at",
    "updated_at",
]
EXPECTED_INDEXES = [
    "uq_external_effect_job_tenant_idempotency",
    "idx_external_effect_job_due",
    "idx_external_effect_job_target",
    "idx_external_effect_job_business",
    "idx_external_effect_job_trace",
    "idx_external_effect_job_effect_type",
    "idx_external_effect_attempt_job",
    "idx_external_effect_attempt_trace",
]


def _text(value: Any) -> str:
    return str(value or "").strip()


def external_effect_filters(params: dict[str, Any]) -> dict[str, str]:
    return {
        "effect_type": _text(params.get("effect_type")),
        "status": _text(params.get("status")),
        "target_type": _text(params.get("target_type")),
        "target_id": _text(params.get("target_id")),
        "business_type": _text(params.get("business_type")),
        "business_id": _text(params.get("business_id")),
        "trace_id": _text(params.get("trace_id")),
    }


def _public_filters(filters: dict[str, Any]) -> dict[str, str]:
    return {key: _text(value) for key, value in filters.items() if _text(value)}


def _execution_summary() -> dict[str, Any]:
    settings = webhook_execution_settings()
    allowed = [item for item in settings["allowed_types"] if item in set(settings["supported_types"])]
    real_execution_enabled = bool(settings["enabled"] and allowed)
    if not settings["enabled"]:
        mode = "disabled"
    elif real_execution_enabled:
        mode = "executable"
    else:
        mode = "shadow"
    return {
        "execution_mode": mode,
        "real_execution_enabled": real_execution_enabled,
        "allowed_effect_types": list(settings["allowed_types"]),
        "executable_effect_types": allowed,
        "supported_effect_types": list(settings["supported_types"]),
        "webhook_execution": settings,
    }


def build_external_effect_jobs_payload(
    params: dict[str, Any],
    *,
    service: ExternalEffectService | None = None,
    current_base_url: str = "",
) -> dict[str, Any]:
    service = service or ExternalEffectService()
    filters = external_effect_filters(params)
    limit = _bounded_int(params.get("limit"), default=50, minimum=1, maximum=200)
    offset = _bounded_int(params.get("offset"), default=0, minimum=0, maximum=100000)
    items, total = service.list_jobs(filters, limit=limit, offset=offset)
    counts = service.count_jobs(filters)
    queue_metrics = service.queue_metrics(filters)
    selected_job_id = _bounded_int(params.get("job_id"), default=0, minimum=0, maximum=10**12)
    selected_job = service.get(selected_job_id) if selected_job_id else None
    attempts = service.list_attempts(selected_job_id) if selected_job else []
    receipt_items, receipt_total = service.list_test_receipts({}, limit=10, offset=0)
    recent_jobs, _recent_jobs_total = service.list_jobs({}, limit=50, offset=0)
    test_jobs = [item for item in recent_jobs if item.payload_json.get("execution_scope") == "test_loopback"][:10]
    receipt_metrics = service.test_receipt_metrics()
    return {
        "ok": True,
        "items": [item.to_dict() for item in items],
        "total": total,
        "filters": _public_filters(filters),
        "limit": limit,
        "offset": offset,
        "counts": counts,
        "queue_metrics": queue_metrics,
        "selected_job": selected_job.to_dict() if selected_job else None,
        "attempts": [attempt.to_dict() for attempt in attempts],
        "display_fields": list(JOB_DISPLAY_FIELDS),
        "route_owner": ROUTE_OWNER,
        "real_external_call_executed": False,
        "test_receiver_enabled": test_receiver_enabled(),
        "test_execution_only": test_execution_only_enabled(),
        "current_base_url_detected": current_base_url,
        "recent_test_jobs": [item.to_dict() for item in test_jobs],
        "recent_test_receipts": [item.to_dict() for item in receipt_items],
        "test_receipt_total": receipt_total,
        **receipt_metrics,
        **_execution_summary(),
    }


def build_external_effect_diagnostics_payload(
    params: dict[str, Any] | None = None,
    *,
    service: ExternalEffectService | None = None,
    current_base_url: str = "",
) -> dict[str, Any]:
    service = service or ExternalEffectService()
    filters = external_effect_filters(dict(params or {}))
    counts = service.count_jobs(filters)
    queue_metrics = service.queue_metrics(filters)
    execution = _execution_summary()
    receipt_metrics = service.test_receipt_metrics()
    return {
        "ok": True,
        "route_owner": ROUTE_OWNER,
        "capability_owner": "ai_crm_next/platform_foundation",
        "real_external_call_executed": False,
        "real_execution_enabled": execution["real_execution_enabled"],
        "allowed_effect_types": execution["allowed_effect_types"],
        "execution_mode": execution["execution_mode"],
        "test_receiver_enabled": test_receiver_enabled(),
        "test_execution_only": test_execution_only_enabled(),
        "current_base_url_detected": current_base_url,
        **receipt_metrics,
        "webhook_execution": execution["webhook_execution"],
        "execution_default": "dry_run",
        "adapter_execution_default": "blocked",
        **queue_metrics,
        "schema_contract": {
            "tables": ["external_effect_job", "external_effect_attempt"],
            "idempotency_constraint": "UNIQUE (tenant_id, idempotency_key)",
            "expected_indexes": list(EXPECTED_INDEXES),
            "required_display_fields": list(JOB_DISPLAY_FIELDS),
        },
        "counts": counts,
        "queue_metrics": queue_metrics,
        "filters": _public_filters(filters),
    }


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))
