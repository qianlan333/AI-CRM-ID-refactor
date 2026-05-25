# Phase 4BT Workflow Nodes Fixture Runtime

## Summary

This package implements the fixture/local metadata list and create slice for
`/api/admin/automation-conversion/workflow-nodes*`.

## Architecture boundary

Capability owner: `aicrm_next.automation_engine`.

The runtime behavior is fixture/local only. The API layer parses requests,
calls application query/command objects, and returns JSON. Domain validation
rejects workflow execution, node transition runtime, timers, outbound sends,
external calls, production owner changes, and fallback removal fields. The
fixture repository stores deterministic metadata, idempotency snapshots, audit
events, and rollback payloads in memory.

Production owner unchanged. Legacy fallback retained. Production must not return fixture fake success.

## Business continuity

Current production automation-conversion pages and actions continue to use the
existing production_compat / legacy-forward path. In production or production
data mode, this slice returns a blocked/degraded payload instead of pretending
fixture data is production success.

## Business value

Operators can keep moving the workflow-node migration from planning into a
testable Next-native contract without enabling workflow execution. The slice
validates list/create metadata, idempotency, audit, and rollback shape so later
staging or production-gated work has a safer base.

## Safety / non-goals

- Fixture/local only.
- No production write by default.
- No external calls by default.
- No timer/execution/outbound send by default.
- No workflow execution or node transition runtime.
- No production route owner switch.
- No legacy fallback deletion or narrowing.
- No deploy, nginx, systemd, schema, or migration change.

## Verification

Run:

```bash
python3 tools/check_phase4bt_workflow_nodes_fixture_runtime.py --output-md /tmp/phase4bt_workflow_nodes_fixture_runtime.md --output-json /tmp/phase4bt_workflow_nodes_fixture_runtime.json
python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json
python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json
python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py tests/test_phase4bt_workflow_nodes_fixture_runtime.py -q
python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json
python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json
git diff --check
```

## Risk / rollback

Risk is limited to fixture/local workflow-node contract shape. Rollback is to
revert this PR; production route ownership and legacy fallback remain unchanged.

## Autopilot decision

Autopilot-safe when local checks and GitHub required checks are green and
`tools/check_automerge_eligibility.py` reports `eligible=true`.

## Next action

Advance to the safe `/api/admin/automation-conversion/tasks*` fixture/local
metadata list/create runtime slice. Do not run due tasks, timers, workflow
execution, or outbound sends.

## PR lifecycle

Create, verify, label `autopilot-safe`, and admin-merge after required checks
are green.
