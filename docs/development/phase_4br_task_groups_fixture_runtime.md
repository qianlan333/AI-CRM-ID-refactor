# Phase 4BR Task Groups Fixture Runtime

## Summary

Phase 4BR implements the first safe runtime slice for `/api/admin/automation-conversion/task-groups*`: fixture/local metadata list and create. It adds domain validation, deterministic in-memory fixture storage, idempotent create semantics, audit and rollback payloads, API handlers, and tests.

This package does not switch production route ownership. Production-facing mode returns a degraded/blocked payload instead of fixture fake success.

## Architecture boundary

- Capability owner: `aicrm_next.automation_engine`.
- Runtime paths touched: `aicrm_next/automation_engine/**` only.
- Route family: `/api/admin/automation-conversion/task-groups*`.
- Current production owner remains `production_compat` with `legacy_forward`.
- Legacy fallback remains available.
- Fixture/local task group data must not be reported as production data.

## Business continuity

Current production traffic continues through the legacy-forwarded route family. The new Next native handlers are safe for fixture/local validation and include a production guard that blocks fixture success in production mode. The implementation does not enable task execution, run-due, workflow execution, timers, outbound sends, external calls, production writes, fallback narrowing, or production owner switch.

## Business value

Task groups are an internal metadata surface used to organize automation tasks. Implementing the list/create fixture slice lets Phase 4 move from planning into real Next-native behavior while preserving the current operating path. The idempotency, audit, and rollback payloads make later test DB or staging packages easier to verify without risking live task execution.

## Runtime Slice

- `GET /api/admin/automation-conversion/task-groups`
  - Supports `program_id`, `include_archived`, `limit`, and `offset`.
  - Returns deterministic fixture/local groups ordered by `sort_order` and `id`.
- `POST /api/admin/automation-conversion/task-groups`
  - Requires `group_name` and `idempotency_key`.
  - Supports `program_id`, `group_code`, `sort_order`, `metadata`, and `operator`.
  - Rejects duplicate group names/codes per program.
  - Rejects dangerous execution/send/adapter/timer fields.
  - Returns audit and rollback payloads.

## Safety / non-goals

- Fixture/local only.
- Production owner unchanged.
- Legacy fallback retained.
- No production write by default.
- No external calls by default.
- No task execution, run-due, workflow execution, timer, or outbound send by default.
- No production repository enablement.
- No `production_compat` behavior change.
- No schema/migration/deploy/nginx/systemd change.
- Production must not return fixture fake success.

## Verification

- `python3 tools/check_phase4br_task_groups_fixture_runtime.py --output-md /tmp/phase4br_task_groups_fixture_runtime.md --output-json /tmp/phase4br_task_groups_fixture_runtime.json`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py tests/test_phase4br_task_groups_fixture_runtime.py -q`
- `python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

Local note: the current local Python environment does not have FastAPI/PyYAML installed, so FastAPI TestClient coverage is committed with `pytest.importorskip("fastapi")` for CI while repository/domain tests run locally without FastAPI.

## Risk / rollback

Risk is limited to fixture/local task-group behavior and checker policy. Rollback is to revert this PR. Production remains on `production_compat` / legacy fallback.

## Autopilot decision

Autopilot selected task-groups because the updated delivery policy prefers moving completed planning/schema/fixture-contract candidates into safe fixture/native runtime, and task-groups is first in the preferred implementation order.

## Next action

Phase 4BS should implement the same fixture/local metadata list/create pattern for `/api/admin/automation-conversion/workflows*`, with workflow activation and execution disabled by default.
