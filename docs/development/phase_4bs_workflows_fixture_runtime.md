# Phase 4BS Workflows Fixture Runtime

## Summary

Phase 4BS implements the safe fixture/local runtime slice for `/api/admin/automation-conversion/workflows*`: metadata list and create. It adds workflow DTOs, domain validation, deterministic in-memory fixture storage, idempotent create semantics, audit and rollback payloads, API handlers, and tests.

This package does not activate workflows or execute workflow runtime. Production-facing mode returns a degraded/blocked payload instead of fixture fake success.

## Architecture Boundary

- Capability owner: `aicrm_next.automation_engine`.
- Runtime paths touched: selected `aicrm_next/automation_engine/**` files only.
- Route family: `/api/admin/automation-conversion/workflows*`.
- Current production owner remains `production_compat` with `legacy_forward`.
- Legacy fallback remains available.
- Fixture/local workflow data must not be reported as production data.

## Business Continuity

Current production traffic continues through the legacy-forwarded route family. The new Next native handlers are safe for fixture/local validation and include a production guard that blocks fixture success in production mode. The implementation does not enable workflow activation, workflow execution, node transitions, timers, outbound sends, external calls, production writes, fallback narrowing, or production owner switch.

## Business Value

Workflow metadata is a core automation configuration surface, but its activation/execution path is high risk. Implementing only list/create fixture metadata lets Phase 4 continue real Next-native implementation while preserving the current operating path. The idempotency, audit, and rollback payloads give later test DB or staging packages a concrete contract without risking live automation behavior.

## Runtime Slice

- `GET /api/admin/automation-conversion/workflows`
  - Supports `program_id`, `status`, `include_archived`, `limit`, and `offset`.
  - Returns deterministic fixture/local workflows ordered by `updated_at` and `id` descending.
- `POST /api/admin/automation-conversion/workflows`
  - Requires `workflow_name` and `idempotency_key`.
  - Supports `program_id`, `workflow_code`, `description`, `status`, `segmentation_basis`, `behavior_tier_scheme`, `profile_segment_template_id`, and `operator`.
  - Rejects duplicate workflow codes per program.
  - Rejects dangerous activation/execution/node-runtime/timer/send/adapter fields.
  - Returns audit and rollback payloads.

## Safety / Non-Goals

- Fixture/local only.
- Production owner unchanged.
- Legacy fallback retained.
- No production write by default.
- No external calls by default.
- No workflow activation, workflow execution, node transition runtime, timer, or outbound send by default.
- No production repository enablement.
- No `production_compat` behavior change.
- No schema/migration/deploy/nginx/systemd change.
- Production must not return fixture fake success.

## Verification

- `python3 tools/check_phase4bs_workflows_fixture_runtime.py --output-md /tmp/phase4bs_workflows_fixture_runtime.md --output-json /tmp/phase4bs_workflows_fixture_runtime.json`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py tests/test_phase4bs_workflows_fixture_runtime.py -q`
- `python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

Local note: the current local Python environment does not have FastAPI installed, so FastAPI TestClient coverage is committed with `pytest.importorskip("fastapi")` for CI while repository/domain tests run locally without FastAPI.

## Risk / Rollback

Risk is limited to fixture/local workflows behavior and checker policy. Rollback is to revert this PR. Production remains on `production_compat` / legacy fallback.

## Autopilot Decision

Autopilot selected workflows because Phase 4BR completed task-groups fixture/local list/create and the updated delivery policy prefers moving completed planning/schema/fixture-contract candidates into safe fixture/native runtime. Workflows is next in the preferred implementation order.

## Next Action

Phase 4BT should implement the same fixture/local metadata list/create pattern for `/api/admin/automation-conversion/workflow-nodes*`, with workflow execution, timer, and outbound behavior disabled by default.
