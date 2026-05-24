# Phase 4AR Workflows Metadata Planning

## Summary

Phase 4AR starts `/api/admin/automation-conversion/workflows*` as the next Phase 4 internal_write candidate after task-groups was paused for owner approval in #648.

This package is planning-only. It defines the workflows metadata-only boundary, checker expectations, and the next safe Phase 4AS step. It does not implement runtime behavior or change production traffic.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Fallback / legacy boundary:

- `aicrm_next.integration_gateway`

Current workflows production owner:

- `production_compat` / `legacy_forward`

Target route family:

- `/api/admin/automation-conversion/workflows*`

## Business Continuity

本 PR 只生成 Phase 4AR workflows metadata-only planning package，不连接 staging DB，不连接生产数据，不执行 staging smoke，不写生产，不实现 runtime，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不启用 workflow execution / timer / outbound send，不影响当前自动化运营配置日常业务使用。workflows 当前 production path 仍由 legacy fallback 保持。

## Business Value

Workflows are daily-business-critical automation configuration metadata, but the route family is adjacent to high-risk execution behavior. This planning package lets Phase 4 continue safely by explicitly separating workflow metadata planning from workflow execution, timer, and outbound send paths before any native contract or runtime work is attempted.

## Planned Scope

Phase 4AR only covers planning for:

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

Phase 4AR does not include:

- workflow execution;
- timer execution;
- outbound send;
- run-due;
- workflow-node runtime;
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

Autopilot selected `phase_4ar_workflows_metadata_planning` because #648 paused task-groups before runtime implementation and phase state selected workflows as the next low-risk metadata/config-oriented internal_write candidate.

## Next Action

Phase 4AS may do workflows schema / route surface confirmation. It must not implement runtime behavior, execute workflows, enable timers, send outbound messages, write production, change production owner, remove fallback, or modify `production_compat`.
