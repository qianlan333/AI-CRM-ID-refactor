# Phase 4AQ Task Groups Fixture Native Implementation Owner Decision

## Summary

Phase 4AQ pauses `/api/admin/automation-conversion/task-groups*` before fixture/native runtime implementation and records the owner decision needed to continue.

This is a docs-only decision/deferral package. It does not implement runtime behavior, does not register a Next route, does not connect staging or production data, and does not alter production traffic.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Fallback / legacy boundary:

- `aicrm_next.integration_gateway`

Current task-groups production owner:

- `production_compat` / `legacy_forward`

Candidate being paused:

- `/api/admin/automation-conversion/task-groups*`

Next safe candidate:

- `/api/admin/automation-conversion/workflows*` metadata-only planning

## Business Continuity

本 PR 只生成 Phase 4AQ task-groups fixture/native implementation owner decision package，不连接 staging DB，不连接生产数据，不执行 staging smoke，不写生产，不实现 runtime，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。task-groups 当前 production path 仍由 legacy fallback 保持。

## Business Value

Phase 4AN through Phase 4AP completed task-groups native contract planning, schema/route surface confirmation, and fixture/native contract planning. The next step would be runtime implementation, which is outside the current docs/tools/tests/state-only autopilot scope. This package prevents autopilot from crossing that boundary without owner approval and keeps the overnight loop moving by selecting a new low-risk planning candidate.

## Current Blocker

Task-groups is blocked on explicit owner confirmation for fixture/native runtime implementation.

Owner decision needed:

- Whether to allow Next fixture/native runtime implementation for task-groups list/create.
- Whether update/delete/archive remain deferred.
- Whether fixture/local POST production guard behavior is acceptable.
- Whether idempotency, audit, rollback, and dangerous-field rejection must be implemented in the first runtime slice.
- Which local tests/checkers must be required before any repository adapter planning.

## Why Autopilot Cannot Continue This Candidate

The next task-groups step changes runtime behavior. Even though it would still be fixture/local and not production-owned, runtime implementation is not allowed under the current low-risk autopilot diff scope. Autopilot must pause the candidate and wait for owner approval.

## Safe Next Options

Option A:

- Owner approves task-groups fixture/native implementation for list/create only.
- Phase 4AR may implement the fixture/local contract.
- Still no production owner switch, production write, external call, fallback removal, or `production_compat` change.

Option B:

- Keep task-groups paused.
- Continue Phase 4 with `/api/admin/automation-conversion/workflows*` metadata-only planning.
- Start with planning/schema/route-surface confirmation only.

Option C:

- Owner chooses a different internal_write candidate from backlog.
- Must remain metadata/config oriented and exclude external calls, timer execution, outbound send, production write, and fallback removal.

## Paused Candidate State

Task-groups is paused after completing:

- Phase 4AN native contract planning.
- Phase 4AO schema/legacy route surface confirmation.
- Phase 4AP fixture/native contract planning.

Resume condition:

- explicit owner approval for task-groups fixture/native runtime implementation.

## Next Candidate Selection

Selected next candidate:

- `/api/admin/automation-conversion/workflows*`

Why selected:

- It is a Phase 4 `internal_write` backlog route family under `aicrm_next.automation_engine`.
- It can start with metadata-only planning and route/schema confirmation.
- It keeps legacy fallback retained.
- It remains separate from workflow execution and timer/send behavior.

Guardrails:

- planning only.
- metadata-only subset.
- no execution.
- no outbound send.
- no production write.
- no production owner switch.
- no fallback removal.
- no `production_compat` change.

## Risk / Rollback

Risk is limited to decision/state/checker wording. Rollback is reverting this PR. Runtime behavior, production traffic, route ownership, fallback behavior, schema, migrations, and `production_compat` are unchanged.

## Autopilot Decision

Autopilot selected `phase_4aq_task_groups_fixture_native_implementation_owner_decision` because #647 completed Phase 4AP and the next task-groups step requires runtime implementation approval. This docs-only decision package pauses task-groups and selects workflows metadata-only planning as the next safe candidate.

## Next Action

Phase 4AR may do workflows metadata-only planning / schema and route surface confirmation. It must not implement runtime behavior, change production owner, execute external calls, write production, remove fallback, or modify `production_compat`.
