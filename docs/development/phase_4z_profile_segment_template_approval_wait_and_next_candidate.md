# Phase 4Z Profile Segment Template Approval-Wait And Next Candidate

## Status

Phase 4Z places the profile-segment-template sample chain into approval-wait handoff and selects the next low-risk Phase 4 internal_write candidate.

- profile-segment-template: awaiting production approval/config.
- No production dry-run execution.
- No production DB connection.
- No production write.
- No production repository route enablement.
- No route ownership switch.
- No `production_compat` change.
- Legacy fallback retained.
- No external calls.
- `delete_ready`: false.

No business route is added, removed, or modified. Production facade enabled mode remains owned by the legacy `production_compat` fallback. The SQLAlchemy adapter exists for explicit non-production and approval-gated paths but is not the production route owner.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Production approval / candidate selection boundary:

- `aicrm_next.integration_gateway`

Approval-wait handoff applies to:

- `/api/admin/automation-conversion/profile-segment-templates*`

Candidate selection applies only to the next Phase 4 internal_write family. This PR does not add, remove, or modify any business route.

## Handoff Summary

profile-segment-template has completed the sample-chain assets needed before production approval/config:

- Next native contract.
- Companion idempotency/audit schema.
- SQLAlchemy repository adapter behind an explicit flag.
- Local test DB parity harness.
- Staging smoke package.
- Production read-only dry-run runner/evidence/preflight.
- Final approval/config gate.

Fixture, local_contract, demo, local test DB, and staging-only evidence cannot be treated as production dry-run success.

## Current Blocker

profile-segment-template remains blocked by production approval/config gaps:

- owner approval missing.
- production config review missing.
- production DB env not confirmed.
- read-only/no-write flags not confirmed.
- rollback owner not assigned.
- evidence path not agreed.
- fallback validation plan not confirmed.

## Resume Conditions

profile-segment-template can resume only after all of these are complete:

- automation_engine owner approval.
- integration_gateway owner approval.
- DB/config owner approval.
- business owner approval.
- rollback owner assigned.
- dry-run operator assigned.
- release/config reviewer approval.
- security/data reviewer approval.
- production config review completed.
- production DB env confirmed.
- read-only/no-write flags confirmed.
- evidence path confirmed.
- fallback validation plan confirmed.
- secret redaction confirmed.
- PII redaction confirmed.

## Resume Next Step

If resumed, the next step must be owner-approved production read-only dry-run evidence only:

- Still no write.
- Still no route switch.
- Still no fallback removal.
- Still no `production_compat` change.
- Still no external calls.

## Next Candidate Selection

Selected candidate:

- `/api/admin/automation-conversion/action-templates*`

Capability owner:

- `aicrm_next.automation_engine`

Replacement phase/category:

- `phase_4_internal_write` / `internal_write`

Why selected:

- It is a bounded internal action-template metadata CRUD family.
- It is in the automation_engine domain, so it can reuse the profile-segment-template methodology: native contract, idempotency, audit, rollback, local parity, staging smoke, approval gates, and retained fallback.
- It is lower risk than agents, workflows, workflow-nodes, tasks, and task-groups because the first planning slice can focus on template metadata and validation rather than runtime orchestration, customer state movement, or live dispatch.
- It remains behind the existing legacy `production_compat` fallback owner until a later approved phase.

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

- Phase 4AA must be planning-only first.
- Keep legacy production path and fallback unchanged.
- Define the native contract before any repository adapter.
- Require idempotency, audit, rollback, validation, checker, and test boundaries.
- Block fixture/local_contract success from production claims.
- Require parity, staging smoke, owner approval, production config review, and rollback before production use.

Expected Phase 4AA scope:

- Action-template native contract planning.
- Legacy payload and table mapping discovery.
- Idempotency and audit planning.
- Rollback payload planning.
- Checker and test plan.
- Fallback boundary plan.

Risks:

- Action-template validation drift could affect operator setup if promoted without parity.
- Delete semantics may be more sensitive than create or update and must stay out of the first plan unless separately approved.
- Broad wildcard ownership could accidentally cover adjacent automation workspace routes without strict route-family checks.

Rollback requirement:

- Keep or restore legacy `production_compat` fallback ownership; revert the candidate PR if checker, parity, smoke, or owner approval fails.

Daily business continuity requirement:

- Do not interrupt current automation operations; keep the current production path until native parity, checker, smoke, rollback, and owner approval are complete.

## Business Continuity

本 PR 只生成 Phase 4Z profile-segment-template approval-wait handoff + next Phase 4 candidate selection，不连接生产数据，不执行 dry-run，不写生产，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。profile-segment-template 当前 production path 仍由 legacy fallback 保持。

## Risk / Rollback

Rollback is deleting the Phase 4Z document, YAML, checker, and test, and reverting narrow checker allowlist maintenance if any. Runtime behavior, production data, route ownership, fallback behavior, `production_compat`, schema, and migrations are unchanged.

## Phase 4AA Recommendation

Phase 4AA should plan the `/api/admin/automation-conversion/action-templates*` native contract and guardrails only. It must not directly change production owner, enable external calls, or remove fallback.
