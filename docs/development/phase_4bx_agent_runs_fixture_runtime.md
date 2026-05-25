# Phase 4BX Agent Runs Fixture Runtime Bundle

## Summary

This package implements the safe fixture/local metadata runtime for `/api/admin/automation-conversion/agent-runs*`.
It adds read-only list/detail DTOs, domain validation, fixture repository data, application queries, FastAPI handlers, a package checker, tests, and phase state updates.

## Bundle Type

Bundle type: Fixture native runtime bundle

## Included Stages

- DTOs for agent-run list/detail metadata requests.
- Domain validation for pagination, filters, visibility, and dangerous run/generation/orchestration fields.
- Fixture/local repository list/detail behavior with deterministic seeded runs.
- Application queries and API handlers for fixture/local metadata.
- Production blocked/degraded guard so production mode returns unavailable instead of fixture fake success.
- Package checker, tests, and `phase_execution_state.yaml` updates.

## Excluded Stages

- Production repository enablement.
- Production DB connection or write.
- Production owner switch.
- Legacy fallback removal or narrowing.
- Run creation or live runtime.
- Replay or orchestration.
- Agent output generation.
- Workflow or task runtime.
- LLM, DeepSeek, OpenClaw, MCP, WeCom, Payment, OAuth, or other external calls.
- Timer, run-due, outbound send, canary approval, or `delete_ready=true`.

## Route Family

`/api/admin/automation-conversion/agent-runs*`

## Runtime Behavior

The runtime behavior is fixture/local only. `GET /api/admin/automation-conversion/agent-runs` returns paginated metadata rows with safe filters, and `GET /api/admin/automation-conversion/agent-runs/{run_id}` returns a fixture detail. Default visibility masks contact/user identifiers; console visibility is fixture-local only.

## Production Behavior

Production owner unchanged. No production write by default. No external calls by default. No timer/execution/outbound send by default. Production must not return fixture fake success; production-like mode returns `production_repository_not_enabled` with a 503 response unless a later explicitly approved repository bundle enables a guarded adapter.

## Fallback Behavior

Legacy fallback retained. This bundle does not delete, narrow, or switch production fallback behavior.

## Architecture Boundary

The new code stays inside `aicrm_next.automation_engine` fixture/native metadata boundaries. It does not modify `production_compat`, migrations, deploy files, external adapters, or production route ownership.

## Business Continuity

Existing production behavior remains unchanged because fixture/local responses are blocked in production mode. Operators can continue using legacy production routes while the Next metadata surface gains testable list/detail behavior.

## Business Value

Agent-run metadata is the operational trace surface for automation conversion work. This bundle makes the safe list/detail subset executable for local review without enabling run creation, live runtime, replay, orchestration, generation, or external calls.

## Safety / Non-Goals

This package intentionally excludes live production writes, owner switches, fallback removal, external calls, run creation, live runtime, replay, orchestration, output generation, workflow/task runtime, timers, and outbound send.

## Verification

- `python3 tools/check_phase4bx_agent_runs_fixture_runtime.py --output-md /tmp/phase4bx_agent_runs_fixture_runtime.md --output-json /tmp/phase4bx_agent_runs_fixture_runtime.json`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py tests/test_phase4bx_agent_runs_fixture_runtime.py -q`
- `python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / Rollback

Rollback is a normal git revert of this fixture/native bundle. Since production owner and fallback behavior are unchanged, rollback does not require data migration or production cleanup.

## Autopilot Decision

Autopilot-safe when checks are green and package checker reports `autopilot_deliverable=true`. The diff is bounded to fixture/native runtime, docs, tools, tests, and phase state.

## Next Action

Next bundle recommendation: Phase 4BY agent-replay discovery contract bundle, combining remaining schema/route confirmation, fixture/native contract planning, checker, tests, and phase state. It must keep replay/orchestration/runtime/generation disabled.

## PR Lifecycle

This compressed bundle replaces separate agent-run DTO, domain validation, application query, fixture repository, API handler, checker, test, and state micro-PRs. It is expected to reduce the equivalent PR count by roughly 50-60% while preserving verification quality.
