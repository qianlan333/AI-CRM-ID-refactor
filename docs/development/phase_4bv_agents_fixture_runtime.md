# Phase 4BV Agents Fixture Runtime Bundle

Bundle type: Fixture native runtime bundle

Route family: `/api/admin/automation-conversion/agents*`

## Included Stages

- DTOs for fixture/local agent list and metadata create requests.
- Domain validation for agent metadata, type/status allowlists, JSON payload size, and dangerous runtime field rejection.
- Application query/command handlers for list/create metadata behavior.
- Fixture/local repository seed data, idempotency, audit event, and rollback payload scaffolding.
- FastAPI list/create handlers for fixture/local behavior.
- Production blocked/degraded guard that refuses fixture fake success when production data is active.
- Phase checker, runtime tests, autopilot policy updates, and phase execution state update.

## Excluded Stages

- Production repository enablement.
- Production owner switch.
- Production write.
- Legacy fallback removal or narrowing.
- Agent-run creation or execution.
- LLM, DeepSeek, OpenClaw, MCP, WeCom, or other external runtime calls.
- Timer, workflow execution, task execution, outbound send, replay, orchestration, export, or download runtime behavior.

## Runtime Behavior

The bundle implements fixture/local metadata list and create only. Create operations validate metadata, force `enabled=false`, persist to the in-memory fixture repository, record an audit event, and return a rollback payload for later approved archive/revert work.

Production owner unchanged.
Legacy fallback retained.
No production write by default.
No external calls by default.
No timer/execution/outbound send by default.
Production must not return fixture fake success.

## Production Behavior

When production mode or production data readiness is detected and no explicitly enabled production repository exists, the agent list/create handlers return `production_repository_not_enabled` with HTTP 503. The blocked payload keeps the route owner honest and reports all real side effects as false.

## Fallback Behavior

The legacy production compatibility path remains the production owner. This bundle does not remove fallback behavior, narrow fallback behavior, or authorize a route switch.

## Verification

- `python3 tools/check_phase4bv_agents_fixture_runtime.py --output-md /tmp/phase4bv_agents_fixture_runtime.md --output-json /tmp/phase4bv_agents_fixture_runtime.json`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py tests/test_phase4bv_agents_fixture_runtime.py -q`
- `python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / Rollback

Risk is limited to fixture/local metadata behavior under `aicrm_next/automation_engine`. Rollback is a normal git revert of this bundle; production behavior remains blocked and fallback remains available.

## Next Bundle Recommendation

Continue with a compressed fixture native runtime bundle for `/api/admin/automation-conversion/agent-outputs*`, limited to metadata list/detail behavior and excluding export, download, generation, agent-run execution, and external calls.
