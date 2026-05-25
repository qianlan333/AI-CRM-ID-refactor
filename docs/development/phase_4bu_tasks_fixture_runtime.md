# Phase 4BU Tasks Fixture Runtime

## Summary

This package implements the fixture/local metadata list and create slice for
`/api/admin/automation-conversion/tasks*`.

## Architecture boundary

Capability owner: `aicrm_next.automation_engine`.

The runtime behavior is fixture/local only. The API layer parses requests,
calls application query/command objects, and returns JSON. Domain validation
rejects run-due, task execution, workflow execution, timers, outbound sends,
external calls, production owner changes, and fallback removal fields. The
fixture repository stores deterministic task metadata, idempotency snapshots,
audit events, and rollback payloads in memory.

Production owner unchanged. Legacy fallback retained. Production must not return fixture fake success.

## Business continuity

Current production automation-conversion pages and actions continue to use the
existing production_compat / legacy-forward path. In production or production
data mode, this slice returns a blocked/degraded payload instead of pretending
fixture data is production success.

## Business value

Tasks are the metadata surface closest to automation execution. Implementing
only fixture/local list and metadata create keeps Phase 4 moving into real
Next-native behavior while preserving the live operating path. The slice gives
later test DB, staging, and production-gated packages a concrete idempotency,
audit, and rollback contract without enabling task execution.

## Runtime slice

- `GET /api/admin/automation-conversion/tasks`
  - Supports `program_id`, `workflow_id`, `node_id`, `group_id`, `task_type`,
    `status`, `include_archived`, `limit`, and `offset`.
  - Returns deterministic fixture/local tasks ordered by workflow, node,
    sort order, and id.
- `POST /api/admin/automation-conversion/tasks`
  - Requires `task_name` and `idempotency_key`.
  - Supports `program_id`, `workflow_id`, `node_id`, `group_id`, `task_code`,
    `task_type`, `status`, `sort_order`, `metadata`, `config`, and `operator`.
  - Rejects duplicate task codes per workflow.
  - Rejects dangerous run-due, execution, timer, send, adapter, production
    owner, and fallback-removal fields.
  - Returns audit and rollback payloads.

## Safety / non-goals

- Fixture/local only.
- Production owner unchanged.
- Legacy fallback retained.
- No production write by default.
- No external calls by default.
- No run-due, task execution, workflow execution, timer, or outbound send by default.
- No production repository enablement.
- No `production_compat` behavior change.
- No schema/migration/deploy/nginx/systemd change.
- Production must not return fixture fake success.

## Verification

- `python3 tools/check_phase4bu_tasks_fixture_runtime.py --output-md /tmp/phase4bu_tasks_fixture_runtime.md --output-json /tmp/phase4bu_tasks_fixture_runtime.json`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py tests/test_phase4bu_tasks_fixture_runtime.py -q`
- `python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

Local note: FastAPI TestClient coverage uses `pytest.importorskip("fastapi")`
so CI can exercise API routes when FastAPI is available, while repository and
domain tests remain runnable locally without live services.

## Risk / rollback

Risk is limited to fixture/local task metadata behavior and checker policy.
Rollback is to revert this PR. Production remains on `production_compat` /
legacy fallback.

## Autopilot decision

Autopilot selected tasks because Phase 4BT completed workflow-nodes
fixture/local list/create and the delivery policy prefers moving completed
planning/schema/fixture-contract candidates into safe fixture/native runtime.
Tasks are next in the preferred implementation order.

## Next action

Phase 4BV should implement the same fixture/local metadata list/create pattern
for `/api/admin/automation-conversion/agents*`, with agent-run execution,
LLM/DeepSeek generation, OpenClaw/MCP, and external calls disabled by default.

## PR lifecycle

Create, verify, label `autopilot-safe`, and admin-merge after required checks
are green.
