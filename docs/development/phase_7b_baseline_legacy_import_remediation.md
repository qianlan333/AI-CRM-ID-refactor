# Phase 7B Baseline Legacy Import Remediation

## Status

- status: phase_7b_baseline_legacy_import_remediation
- bundle_type: phase_7b_baseline_legacy_import_remediation_bundle
- cleanup_family: baseline_direct_legacy_import_remediation
- direct legacy import blockers before: 3
- direct legacy import blockers after: 0
- production behavior changed: false
- production_compat behavior changed: false
- fallback removed: false
- legacy runtime deleted: false
- delete_ready: false

## Scope

Phase 7B remediates the three Phase 1-6 baseline direct legacy import blockers by moving the legacy imports behind the existing integration boundary in `aicrm_next/integration_gateway/legacy_flask_facade.py`. It keeps the same legacy functions, return contracts, guard checks, queue payloads, and app-context behavior.

## Remediated Blockers

- `aicrm_next/automation_engine/group_ops/domain.py:10` no longer imports `wecom_ability_service.domains.tasks.private_message` directly.
- `aicrm_next/integration_gateway/wecom_group_adapter.py:97` no longer imports `wecom_ability_service.wecom_client` directly.
- `aicrm_next/integration_gateway/wecom_group_adapter.py:155` no longer imports `wecom_ability_service.domains.broadcast_jobs` directly.

## Boundary Shape

`legacy_flask_facade.py` remains the single allowed dynamic legacy loader surface. New helper functions expose the same legacy payload builder, WeCom client factory, and broadcast queue enqueue call through that boundary. FastAPI/Starlette response classes are lazily imported so pure domain tests can import the boundary without requiring FastAPI in the local environment.

## Behavior Evidence

The group-ops domain validation, queue contract, and webhook API tests pass with the new boundary. `tools/check_legacy_facade_growth_freeze.py` passes with zero direct legacy import findings.

## Non-Goals

This bundle does not remove fallback, change production_compat behavior, delete legacy runtime, change live WeCom client behavior, switch production owners, execute timers, run automation, send outbound traffic, change payment behavior, cut over OAuth callbacks, cut over WeCom callbacks, or run destructive migrations.

## Next

The selected next bundle is `phase_7c_delete_ready_candidate_selection_bundle`, which should build the cleanup candidate matrix without authorizing runtime deletion or fallback removal.
