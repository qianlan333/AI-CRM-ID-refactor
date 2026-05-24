# Phase 4AV Workflow Nodes Metadata Planning

## Summary

Phase 4AV starts `/api/admin/automation-conversion/workflow-nodes*` as the next Phase 4 internal_write candidate after workflows was paused for owner approval in #652.

This package is planning-only. It defines the workflow-nodes metadata-only boundary, checker expectations, and the next safe Phase 4AW step. It does not implement runtime behavior or change production traffic.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Fallback / legacy boundary:

- `aicrm_next.integration_gateway`

Current workflow-nodes production owner:

- `production_compat` / `legacy_forward`

Target route family:

- `/api/admin/automation-conversion/workflow-nodes*`

## Business Continuity

本 PR 只生成 Phase 4AV workflow-nodes metadata-only planning package，不连接 staging DB，不连接生产数据，不执行 staging smoke，不写生产，不实现 runtime，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不启用 workflow execution / timer / outbound send，不影响当前自动化运营配置日常业务使用。workflow-nodes 当前 production path 仍由 legacy fallback 保持。

## Business Value

Workflow nodes define the structure around workflow behavior, but node execution, transitions, timer behavior, and outbound send are high-risk paths. This planning package lets Phase 4 continue safely by separating workflow-node metadata planning from execution behavior before any native contract or runtime work is attempted.

## Planned Scope

Phase 4AV only covers planning for:

- route surface confirmation;
- metadata-only subset decision;
- request/response field mapping plan;
- validation boundary plan;
- idempotency plan;
- audit plan;
- rollback payload plan;
- fixture/local contract plan;
- checker and test plan.

## Explicit Exclusions

Phase 4AV does not include:

- workflow execution;
- workflow activation;
- timer execution;
- run-due;
- outbound send;
- workflow transition runtime;
- task runtime;
- WeCom / Payment / OAuth / OpenClaw / MCP real calls;
- production write;
- production owner switch;
- fallback removal;
- `production_compat` change;
- schema or migration change.

## Guardrails

- Keep legacy fallback retained.
- Keep production owner on `production_compat`.
- Treat fixture/local evidence as non-production evidence.
- Require metadata-only contract before any implementation.
- Require explicit owner approval before crossing into workflow execution, timer, outbound send, or production write.

## Risk / Rollback

Risk is limited to documentation, checker, test, and phase state wording. Rollback is reverting this PR. Runtime behavior, production traffic, route ownership, fallback behavior, schema, migrations, deploy config, and `production_compat` are unchanged.

## Autopilot Decision

Autopilot selected `phase_4av_workflow_nodes_metadata_planning` because #652 paused workflows before runtime implementation and phase state selected workflow-nodes as the next low-risk metadata/config-oriented internal_write candidate.

## Next Action

Phase 4AW may do workflow-nodes schema / route surface confirmation. It must not implement runtime behavior, execute workflows, enable timers, send outbound messages, write production, change production owner, remove fallback, or modify `production_compat`.
