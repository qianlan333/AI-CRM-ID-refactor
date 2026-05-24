# Phase 4A Internal Write Candidate Selection

Status: Phase 4A planning only. This document does not change runtime behavior,
implement a write route, delete fallback, narrow `production_compat`, enable
real external calls, modify database schema, authorize production cutover, or
mark any route as `delete_ready`.

## Goal

Phase 4A selects and risk-ranks the first low-risk internal_write candidates
from `legacy_replacement_backlog.yaml`. It also establishes implementation
guardrails for a later Phase 4B PR. It does not implement any candidate.

## Candidate Screening Rules

A first-batch Phase 4 candidate must satisfy all of these before it can move
from planning to implementation:

- `replacement_phase: phase_4_internal_write`
- `replacement_category: internal_write`, or a shell/navigation route with a
  clearly bounded internal-write subset.
- `external_side_effect_risk` is not `real_blocked`, `real_allowed`, or an
  external provider call.
- It is not Payment, OAuth, WeCom external call, timer, automation execution,
  media upload, OpenClaw, or MCP.
- `fallback_required_until` is non-empty.
- `rollback_path` is non-empty.
- `checker` is non-empty.
- If `daily_business_critical` is true, `business_continuity_requirement` is
  non-empty and keeps the current production path available.

## Forbidden First Batch

These route families cannot enter the first Phase 4 implementation batch:

- Payment, WeChat Pay, Alipay, checkout, or orders write.
- OAuth, `auth/wecom`, or WeChat H5 OAuth.
- WeCom callback or external-contact callback.
- timer, run-due, or campaign run-due.
- automation execution, send, run center, or outbound task execution.
- media upload, image upload, attachment upload, or miniprogram upload.
- OpenClaw or MCP real external call.
- public questionnaire submit or public H5 write with external push.

## Evaluated Candidates

### Candidate A: Questionnaire Admin Draft Create/Update Only

- route_family: `/api/admin/questionnaires*`, narrowed to admin draft
  create/update only.
- capability_owner: `aicrm_next.questionnaire`
- current_runtime_owner: `next`
- production_behavior: `guarded_preview`
- why_candidate: The backlog classifies this family as
  `phase_4_internal_write` / `internal_write`, and an admin draft-only slice
  could be bounded if it excludes public and external paths.
- why_not_now / risk: The route family also contains enable/delete/export and is
  adjacent to public submit, OAuth, diagnostics write, and external push.
- excluded_side_effects: public submit, OAuth, diagnostics write, external push,
  enable/delete/export, Payment, WeCom external call, timer, automation
  execution, media upload, OpenClaw/MCP real external call.
- required_idempotency: Define draft create idempotency key or duplicate-title
  protection, and update version checks.
- required_audit_operator_identity: Require admin operator identity for every
  create/update command.
- required_validation: Preserve validation error shape for missing title, invalid
  schema, invalid visibility, and stale update.
- required_rollback: Draft restore or compensating update path must be proven
  before implementation.
- fallback_required_until: Next draft write parity, checker, smoke, rollback,
  and owner approval are all complete.
- required_checker: A Phase 4B questionnaire draft checker that proves no public
  submit/OAuth/external push path is touched.
- required_smoke: Admin draft create/update smoke in a non-production fixture
  context plus production-safe degraded path smoke.
- business_continuity_requirement: Current questionnaire admin and public
  questionnaire daily paths must keep working; fallback remains retained.
- decision: evaluate_later

### Candidate B: Automation Profile Segment Template Internal CRUD Only

- route_family: `/api/admin/automation-conversion/profile-segment-templates*`
- capability_owner: `aicrm_next.automation_engine`
- current_runtime_owner: `production_compat`
- production_behavior: `legacy_forward`
- why_candidate: The backlog classifies this route family as
  `phase_4_internal_write` / `internal_write`; it is narrower than execution,
  send, agent orchestration, and timer families and can be treated as internal
  metadata CRUD.
- why_not_now / risk: It is still a daily automation workspace surface and is
  currently legacy-forwarded, so Phase 4B must preserve fallback and avoid
  changing execution semantics.
- excluded_side_effects: run-due, workflow execution, send, outbound task
  dispatch, agent orchestration, WeCom external call, OpenClaw/MCP real external
  call, Payment, OAuth, timer, media upload.
- required_idempotency: Define stable template identifier handling, duplicate
  name protection, and update version or last-modified checks.
- required_audit_operator_identity: Require admin operator identity for create,
  update, and delete commands.
- required_validation: Preserve validation error shape for missing name, invalid
  segment criteria, invalid template payload, duplicate template, and stale
  update.
- required_rollback: Template restore or compensating update/delete path must be
  documented and smoke-tested before any fallback narrowing.
- fallback_required_until: Next internal metadata CRUD parity, checker, smoke,
  rollback, and owner approval are all complete.
- required_checker: A Phase 4B profile-segment-template checker that blocks
  execution/send/timer/external-call changes and verifies idempotency/audit
  guards.
- required_smoke: Admin template CRUD smoke in a safe environment plus
  production-safe fallback/degraded smoke without real external calls.
- business_continuity_requirement: Current automation workspace daily use must
  not be interrupted; legacy fallback and `production_compat` remain retained.
- decision: recommended

### Candidate C: Automation Action Template / Task Group Metadata CRUD Only

- route_family:
  `/api/admin/automation-conversion/action-templates*` and
  `/api/admin/automation-conversion/task-groups*`, narrowed to internal metadata
  CRUD only.
- capability_owner: `aicrm_next.automation_engine`
- current_runtime_owner: `production_compat`
- production_behavior: `legacy_forward`
- why_candidate: Both route families are backlog `phase_4_internal_write` /
  `internal_write` entries and may be bounded as metadata CRUD if execution and
  dispatch paths are excluded.
- why_not_now / risk: Action templates and task groups are closer to workflow
  behavior and task dispatch than profile segment templates, so they need
  stronger proof that no execution/send path is included.
- excluded_side_effects: workflow execution, task dispatch, outbound send,
  run-due, agent orchestration, WeCom external call, OpenClaw/MCP real external
  call, Payment, OAuth, timer, media upload.
- required_idempotency: Define duplicate name protection, stable metadata IDs,
  and update version checks for both families.
- required_audit_operator_identity: Require admin operator identity for every
  create, update, and delete command.
- required_validation: Preserve validation error shape for missing action/task
  group name, invalid metadata payload, duplicate entry, and stale update.
- required_rollback: Metadata restore or compensating update/delete path must be
  documented before implementation.
- fallback_required_until: Next metadata CRUD parity, checker, smoke, rollback,
  and owner approval are all complete.
- required_checker: A Phase 4B metadata checker that proves execution, dispatch,
  send, timer, and external-call paths remain excluded.
- required_smoke: Admin metadata CRUD smoke in a safe environment plus
  production-safe fallback/degraded smoke without real external calls.
- business_continuity_requirement: Current automation workspace daily use and
  execution safe-mode must not be interrupted; fallback remains retained.
- decision: evaluate_later

## Phase 4B First Candidate Recommendation

Recommended candidate: Candidate B,
`/api/admin/automation-conversion/profile-segment-templates*`, as a bounded
internal metadata CRUD route family.

This recommendation does not authorize implementation. It only identifies the
least risky first planning target because it is narrower than public
questionnaire writes and farther from workflow execution than action-template or
task-group route families. Phase 4B still requires explicit owner approval and
a separate implementation PR.

## Phase 4 Implementation Guardrails

Any Phase 4B implementation PR must:

- Start with one route family only.
- Preserve legacy fallback.
- Keep `production_compat` unchanged unless explicitly approved.
- Include idempotency or duplicate protection.
- Include audit/operator identity, or an explicit reason why it is not needed.
- Include validation error contract coverage.
- Include rollback data path.
- Include dry-run or preview behavior if business impact exists.
- Include a checker.
- Include smoke verification.
- Avoid fixture/local_contract production success.
- Avoid real external side effects.
