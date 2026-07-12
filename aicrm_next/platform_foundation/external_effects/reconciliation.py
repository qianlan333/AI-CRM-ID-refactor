from __future__ import annotations

from typing import Any

from .repo import ExternalEffectRepository, build_external_effect_repository


RECONCILIATION_COUNT_KEYS = (
    "stale_dispatching_count",
    "unknown_after_dispatch_count",
    "reconciliation_required_count",
    "succeeded_without_evidence_count",
    "simulated_recorded_as_succeeded_count",
    "dispatching_without_active_lease_count",
    "lease_on_non_dispatching_count",
)


class ExternalEffectDispatchReconciliationService:
    """Count-only delivery truth diagnostics; it never repairs or dispatches."""

    def __init__(self, repository: ExternalEffectRepository | None = None):
        self._repo = repository or build_external_effect_repository()

    def diagnose(self) -> dict[str, Any]:
        metrics = self._repo.queue_metrics({})
        counts = {key: int(metrics.get(key) or 0) for key in RECONCILIATION_COUNT_KEYS}
        return {
            "ok": True,
            "mode": "count_only",
            "repair_supported": False,
            "database_mutation_performed": False,
            "real_external_call_executed": False,
            "pii_in_output": False,
            "has_anomalies": any(counts.values()),
            "counts": counts,
        }
