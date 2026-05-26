# Phase 7A Legacy Retirement Readiness

## Status

- status: phase_7a_legacy_retirement_readiness
- bundle_type: phase_7a_legacy_retirement_readiness_bundle
- route_family: phase_7_legacy_retirement_readiness
- production behavior changed: false
- production_compat behavior changed: false
- fallback removed: false
- legacy runtime deleted: false
- delete_ready: false

## Phase 6 Handoff

Phase 6L closed the readiness and acceptance loop without production owner switches, fallback removal, production_compat behavior changes, timer/default execution, outbound send, live external default-on behavior, destructive migration, or delete_ready authorization. Phase 7 starts from that baseline and may only classify, inventory, and prepare cleanup until a later explicit gate approves behavior-changing work.

## Retirement Scope

Phase 7A defines cleanup rules only. It does not delete runtime code, remove fallback, change production_compat behavior, switch route owners, alter deploy config, change timer or automation execution, touch outbound send, or alter payment, OAuth callback, or WeCom callback behavior.

## Cleanup Rules

Fallback cleanup requires owner approval, usage evidence, route ownership evidence, shadow compare where behavior could differ, and rollback evidence. production_compat cleanup requires exact-route shadow compare and rollback. Legacy runtime deletion requires usage evidence proving the route is no longer owned or reached by production. `delete_ready` cannot become true in Phase 7A.

## Baseline Blockers

- `aicrm_next/automation_engine/group_ops/domain.py:10` directly imports `wecom_ability_service.domains.tasks.private_message`.
- `aicrm_next/integration_gateway/wecom_group_adapter.py:97` directly imports `wecom_ability_service.wecom_client`.
- `aicrm_next/integration_gateway/wecom_group_adapter.py:155` directly imports `wecom_ability_service.domains.broadcast_jobs`.
- `tools/check_architecture_skill_compliance.py` can be blocked in local environments without `yaml`; that is an environment blocker, not a pass.

## Candidate Classification

Safe no-behavior-change cleanup candidates are docs, checker, state, allowlist, and import-boundary refactors that keep runtime behavior identical. Shadow-compare candidates include exact production_compat route cleanup and owner-switch-adjacent route families. Owner approval is required before fallback removal. Production owner switch evidence is required before any runtime retirement. Payment, OAuth callback, WeCom callback, timer, automation execution, outbound send, destructive migration, and runtime fallback deletion are not safe for the Phase 7 first batch.

## Phase 7B Candidate

The selected next bundle is `phase_7b_baseline_legacy_import_remediation_bundle`. It should first attempt a no-behavior-change import boundary cleanup for the direct legacy imports above. If safe remediation would alter live behavior, it must record the blocker and stop or stay plan-only.

## Non-Goals

This bundle does not remove fallback, change production_compat behavior, delete legacy runtime, set `delete_ready: true`, switch production route ownership, execute timers, run automation, send outbound traffic, change payment behavior, cut over OAuth callbacks, cut over WeCom callbacks, or run destructive migrations.
