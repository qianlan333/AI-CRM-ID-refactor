# Phase 4BB Tasks Schema Route Surface Confirmation

## Summary

Phase 4BB confirms the legacy route surface and schema references for `/api/admin/automation-conversion/tasks*` before any fixture/native contract planning. It keeps the recommended future native subset to metadata list/create only.

This PR is docs/YAML/checker/test/state only. It does not implement runtime behavior, execute task runners, connect to DBs, or change production ownership.

## Architecture boundary

- Capability owner: `aicrm_next.automation_engine`.
- Integration/fallback boundary: `aicrm_next.integration_gateway`.
- Current runtime owner: `production_compat`.
- Production behavior: `legacy_forward`.
- Legacy fallback remains retained.
- Fixture/local evidence remains non-production evidence.

## Business continuity

Production continues to use the existing legacy-forwarded task APIs. This package does not connect to staging DB or production DB, does not write production, does not switch route owner, does not modify `production_compat`, does not remove fallback, and does not enable task execution, workflow execution, timer execution, outbound send, or real external calls.

## Confirmed Route Surface

The production compatibility layer forwards:

- `/api/admin/automation-conversion/tasks`
- `/api/admin/automation-conversion/tasks/{path}`

The legacy application registers:

- `GET /api/admin/automation-conversion/tasks`
- `POST /api/admin/automation-conversion/tasks`
- `GET /api/admin/automation-conversion/tasks/<task_id>`
- `PUT /api/admin/automation-conversion/tasks/<task_id>`
- `POST /api/admin/automation-conversion/tasks/<task_id>/copy`
- `POST /api/admin/automation-conversion/tasks/<task_id>/activate`
- `POST /api/admin/automation-conversion/tasks/<task_id>/pause`
- `DELETE /api/admin/automation-conversion/tasks/<task_id>`
- `POST /api/admin/automation-conversion/tasks/<task_id>/preview-audience`
- `POST /api/admin/automation-conversion/tasks/run-due`

Phase 4BB only recommends list/create metadata as the first future native subset. Every other route remains deferred.

## Confirmed Schema

Main table:

- `automation_operation_task`

Important columns:

- `id`
- `program_id`
- `group_id`
- `task_name`
- `description`
- `status`
- `trigger_type`
- `send_time`
- `timezone`
- `target_audience_code`
- `target_stage_code`
- `audience_day_offset`
- `behavior_filter`
- `content_mode`
- `profile_segment_template_id`
- `unified_content_json`
- `segment_contents_json`
- `agent_config_json`
- `created_by`
- `updated_by`
- `created_at`
- `updated_at`
- `published_at`

Indexes:

- `idx_automation_operation_task_program`
- `idx_automation_operation_task_group`

Related tables:

- `automation_operation_task_group`
- `automation_operation_task_execution`
- `automation_operation_task_execution_item`
- `automation_profile_segment_template`

Execution tables are confirmed only so they can remain outside the metadata subset.

## First Native Subset Recommendation

Future Phase 4BC planning should cover only:

- `list_operation_tasks`
- `create_operation_task_metadata_only`

The create path must still treat status, trigger, content, and audience fields as metadata. It must not enqueue jobs, send messages, or execute workflows.

## Deferred Scope

- task detail
- task update
- task copy
- task activate/pause
- task delete/archive
- preview audience
- run-due
- task execution
- workflow execution
- timer execution
- outbound send
- real external calls
- production write
- production route owner switch
- fallback removal
- `production_compat` change

## Business value

This narrows the tasks migration path to a verifiable metadata contract before any runtime work. It protects current automation operations from accidental runner activation while preserving a clear route/schema map for the next fixture/native planning phase.

## Verification

- `python3 tools/check_phase4bb_tasks_schema_route_surface_confirmation.py --output-md /tmp/phase4bb_tasks_schema_route_surface_confirmation.md --output-json /tmp/phase4bb_tasks_schema_route_surface_confirmation.json`
- `python3 tools/check_phase4ba_tasks_metadata_plan.py --output-md /tmp/phase4ba_tasks_metadata_plan.md --output-json /tmp/phase4ba_tasks_metadata_plan.json`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py tests/test_phase4ba_tasks_metadata_plan.py tests/test_phase4bb_tasks_schema_route_surface_confirmation.py -q`
- `python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / rollback

Risk is limited to static documentation/checker/state misclassification. Rollback is to revert this PR. Production traffic remains on `production_compat` and legacy fallback.

## Autopilot decision

Autopilot selected one bounded low-risk work package: Phase 4BB tasks schema/route surface confirmation. It records #658 as the latest merged autopilot PR and sets Phase 4BC fixture/native contract planning as the next allowed action.

## Next action

Phase 4BC should plan the fixture/native list/create metadata contract for tasks. It must not implement runtime ownership, execute run-due, write production, switch production owner, remove fallback, enable outbound send, or enable real external calls.
