# Phase 4AM Action Templates Staging Wait And Next Candidate

## Status

Phase 4AM places action-templates into staging approval/config wait and selects the next low-risk Phase 4 internal_write candidate.

- action-templates: awaiting staging approval/config.
- No staging smoke execution.
- No staging DB connection.
- No production DB connection.
- No production write.
- No production repository route enablement.
- No route ownership switch.
- No `production_compat` change.
- Legacy fallback retained.
- No external calls.
- `delete_ready`: false.

No business route is added, removed, or modified. The action-templates production path remains owned by the legacy `production_compat` fallback.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Staging approval / candidate selection boundary:

- `aicrm_next.integration_gateway`

Approval-wait handoff applies to:

- `/api/admin/automation-conversion/action-templates*`

Candidate selection applies only to the next Phase 4 internal_write family.

## Handoff Summary

action-templates has completed the staged assets needed before staging approval/config:

- schema/route/service confirmation.
- companion idempotency/audit schema planning.
- additive companion migration artifact.
- fixture/local native contract.
- local fixture parity harness.
- SQLAlchemy repository adapter behind an explicit flag.
- local/test DB adapter parity harness.
- staging smoke package.
- staging smoke evidence gate.
- staging execution readiness gate.

Fixture, local contract, local test DB, and staging-only evidence cannot be treated as production route-switch success.

## Current Blockers

action-templates remains waiting on staging approval/config gaps:

- staging DB/config owner approval missing.
- staging DB env not confirmed.
- staging DB URL safety not confirmed.
- smoke operator not assigned.
- rollback owner not assigned.
- evidence path not agreed.
- write smoke approval not confirmed.
- safe namespace cleanup strategy not confirmed.

## Resume Conditions

action-templates can resume only after all of these are complete:

- automation_engine owner approval.
- integration_gateway owner approval.
- staging DB/config owner approval.
- rollback owner assigned.
- smoke operator assigned.
- staging DB env confirmed.
- staging DB URL safety confirmed.
- repo backend confirmed.
- read-only preflight confirmed.
- write smoke approval confirmed if writes are needed.
- safe namespace confirmed.
- evidence path confirmed.
- cleanup strategy confirmed.
- side-effect safety confirmed.

## Resume Next Step

If resumed, the next action-templates step must be owner-approved staging smoke evidence only:

- Still no production write.
- Still no production route owner switch.
- Still no fallback removal.
- Still no `production_compat` change.

## Next Candidate Selection

Selected candidate:

- `/api/admin/automation-conversion/task-groups*`

Capability owner:

- `aicrm_next.automation_engine`

Replacement phase/category:

- `phase_4_internal_write` / `internal_write`

Why selected:

- It is a bounded internal task-group metadata family in the same automation_engine domain.
- It can reuse the profile-segment-template and action-templates methodology: schema confirmation, native contract planning, idempotency, audit, rollback, local parity, staging gates, and retained fallback.
- It is lower risk than tasks, workflows, workflow-nodes, agents, agent-runs, and executions because the first Phase 4AN slice can stay focused on group metadata and validation rather than workflow orchestration or runtime dispatch.
- It is already listed in the legacy replacement backlog and production route ownership manifest as a Phase 4 internal_write candidate owned by `aicrm_next.automation_engine`.

Excluded side effects:

- Payment.
- OAuth.
- WeCom external calls.
- Callback handling.
- run-due paths.
- Timers.
- Automation runtime actions.
- Outbound sends.
- Media uploads.
- OpenClaw / MCP real calls.
- Public submits.
- External pushes.

Required guardrails:

- Phase 4AN must be implementation/native-contract planning only.
- Keep legacy production path and fallback unchanged.
- Confirm route surface before implementation.
- Define idempotency, audit, rollback, validation, checker, and test boundaries before any repository adapter.
- Block fixture/local/test/staging evidence from production claims.
- Require staging smoke, owner approval, production config review, and rollback before production use.

Expected Phase 4AN scope:

- task-groups route surface confirmation.
- legacy payload and table mapping discovery.
- safe metadata-only scope decision.
- idempotency and audit planning.
- rollback payload planning.
- checker and test plan.
- fallback boundary plan.

Risks:

- task-group writes may affect operator organization if promoted without parity.
- broad wildcard ownership could accidentally include task runtime or orchestration paths without strict route-family checks.
- update/delete semantics may be more sensitive than create and should stay out of the first plan unless separately approved.

Rollback requirement:

- Keep or restore legacy `production_compat` fallback ownership; revert the candidate PR if checker, parity, smoke, or owner approval fails.

Daily business continuity requirement:

- Do not interrupt current automation operations setup; keep the current production path until native parity, checker, smoke, rollback, and owner approval are complete.

## Business Continuity

本 PR 只生成 Phase 4AM action-templates staging-approval-wait handoff + next Phase 4 candidate selection，不连接 staging DB，不连接生产数据，不执行 staging smoke，不写生产，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。action-templates 当前 production path 仍由 legacy fallback 保持。

## Risk / Rollback

Rollback is deleting the Phase 4AM document, YAML, checker, and test, and reverting narrow checker allowlist maintenance if any. Runtime behavior, staging data, production data, route ownership, fallback behavior, `production_compat`, schema, and migrations are unchanged.

## Phase 4AN Recommendation

Phase 4AN should plan the `/api/admin/automation-conversion/task-groups*` native contract and guardrails only. It must not directly change production owner, execute external calls, or remove fallback.
