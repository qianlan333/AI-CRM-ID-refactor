# Phase 4AN Task Groups Native Contract Plan

## Summary

Phase 4AN starts the next low-risk Phase 4 internal_write candidate after action-templates was paused by owner decision package #644. This package plans the native contract for `/api/admin/automation-conversion/task-groups*` only.

No runtime implementation is included.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Fallback / legacy boundary:

- `aicrm_next.integration_gateway`

Route family:

- `/api/admin/automation-conversion/task-groups*`

Current production owner:

- `production_compat` / `legacy_forward`

This PR only changes docs, YAML, checker/tests, and autonomous phase state. It does not add, remove, or modify any business route.

## Business Continuity

本 PR 只生成 Phase 4AN task-groups native contract planning，不连接 staging DB，不连接生产数据，不执行 staging smoke，不写生产，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。task-groups 当前 production path 仍由 legacy fallback 保持。

## Business Value

Action-templates is paused awaiting staging owner/config decisions. Moving to task-groups planning keeps Phase 4 advancing on a low-risk metadata/config route family without touching production traffic. The plan defines route scope, expected contract, validation, idempotency, audit, rollback, and future checker gates before any implementation work.

## Selected Candidate

Selected route family:

- `/api/admin/automation-conversion/task-groups*`

Why selected:

- It was selected in the Phase 4AM handoff as the next lower-risk Phase 4 internal_write candidate.
- It is an internal automation metadata/config family.
- It avoids Payment, OAuth, WeCom external calls, timer execution, outbound send, media upload, and real OpenClaw/MCP calls.
- The production route ownership manifest and legacy replacement backlog both list it as `aicrm_next.automation_engine`, `production_compat`, `legacy_forward`, with legacy fallback retained.

## Planned Native Contract Scope

Phase 4AN planning is limited to native contract discovery and guardrails:

- confirm route surface for GET/POST/PUT/PATCH/DELETE/OPTIONS/HEAD.
- identify metadata-only subset for the first future implementation slice.
- document request/response fields before implementation.
- define validation boundaries.
- define idempotency and audit expectations for future writes.
- define rollback payload requirements.
- define fixture/local contract boundaries.
- define checker and test expectations.

## Explicit Non-goals

This package does not authorize:

- runtime implementation.
- production dry-run.
- production write.
- production repository route enablement.
- route ownership switch.
- fallback removal.
- `production_compat` change.
- real external calls.
- timer or automation execution.
- outbound send.
- update/delete/detail expansion beyond planning.
- canary approval.
- `delete_ready`.

## Contract Planning Questions

Future implementation planning must answer:

1. Which legacy handler owns task-group list/create/update/delete today?
2. Which table(s) store task-group metadata?
3. Which fields are metadata-only and safe for fixture/local native contract first?
4. Which writes need idempotency keys?
5. Which audit fields are required for create/update/archive?
6. What rollback payload is sufficient to revert a created or changed task group?
7. Which status/category/name/code validation rules exist in legacy?
8. Which paths could trigger workflow execution, scheduling, outbound send, or external calls and must remain excluded?
9. Which local fixture contract should be built before repository adapter planning?
10. Which staging/production evidence is required before any owner switch?

## Guardrails

- Keep production path on legacy fallback.
- Keep fixture/local/test/staging evidence separate from production success claims.
- Keep execution-like task paths out of the first contract.
- Keep update/delete/archive out of implementation until separately planned.
- Require idempotency, audit, rollback, and side-effect safety before any native write implementation.
- Require owner approval before staging smoke, production dry-run, production write, route ownership switch, or fallback removal.

## Risk / Rollback

Risk is limited to planning/checker wording. Rollback is reverting this PR. Runtime behavior, staging data, production data, route ownership, fallback behavior, `production_compat`, schema, and migrations are unchanged.

## Autopilot Decision

Autopilot selected `phase_4an_task_groups_native_contract_planning` because action-templates is paused by #644 and task-groups is the next lower-risk Phase 4 internal_write candidate. This is a bounded low-risk docs/checker/test/state work package.

## Next Action

Phase 4AO may do task-groups schema/legacy route surface confirmation or fixture/native contract planning. It must not change production owner, execute external calls, write production, remove fallback, or modify `production_compat`.
