# Phase 4AZ Next Internal Write Candidate Selection

## Summary

Phase 4AZ records the next low-risk Phase 4 internal_write candidate after workflow-nodes was paused by #656. The selected candidate is `/api/admin/automation-conversion/tasks*`, but the next package is planning only.

This package is docs/checker/test/state only. It does not implement runtime behavior.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Integration fallback boundary:

- `aicrm_next.integration_gateway`

Current production owner for the selected candidate:

- `production_compat` / `legacy_forward`

Selected route family:

- `/api/admin/automation-conversion/tasks*`

## Business Continuity

本 PR 只生成 Phase 4AZ next internal_write candidate selection package，不连接 staging DB，不连接生产数据，不执行 staging smoke，不写生产，不实现 runtime，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不启用 task execution / workflow execution / run-due / timer / outbound send，不影响当前自动化运营配置日常业务使用。tasks 当前 production path 仍由 legacy fallback 保持。

## Business Value

The previous Phase 4 candidates are now paused at owner-decision gates. Selecting a fresh bounded candidate keeps migration work moving without forcing runtime implementation or production changes. Task metadata is useful for automation configuration planning, while run-due and execution behavior can remain explicitly out of scope.

## Why Tasks

Tasks are selected because they are a known Phase 4 internal_write route family in the manifest and backlog. They can start with metadata planning, list/create contract planning, idempotency/audit/rollback expectations, and checker/test scope.

Agents and agent-runs are deferred because they are closer to agent/LLM/runtime execution surfaces. Task run-due and execution paths are excluded from this selection.

## Required Guardrails

- Planning only.
- Metadata-only subset.
- No runtime implementation.
- No run-due behavior.
- No task execution.
- No workflow execution.
- No timer behavior.
- No outbound send.
- No external calls.
- Keep legacy fallback.
- No production owner switch.
- No production write.

## Safety / Non-Goals

This PR does not:

- implement tasks runtime;
- implement run-due;
- execute tasks or workflows;
- enable timers or outbound send;
- modify business routes;
- modify `production_compat`;
- modify schema or migrations;
- connect to staging or production data;
- write production;
- remove or narrow fallback;
- claim production approval.

## Risk / Rollback

Risk is limited to docs, YAML, checker, tests, and phase state wording. Rollback is reverting this PR. Runtime behavior, production traffic, route ownership, fallback behavior, schema, migrations, deploy config, and `production_compat` are unchanged.

## Autopilot Decision

Autopilot selected `phase_4az_next_internal_write_candidate_selection` because #656 paused workflow-nodes before runtime implementation and phase state needs a new low-risk Phase 4 internal_write candidate.

## Next Action

Phase 4BA should begin `/api/admin/automation-conversion/tasks*` metadata planning only. It must not implement runtime behavior, run-due, task execution, workflow execution, timers, outbound messages, production owner switch, production write, or fallback removal.
