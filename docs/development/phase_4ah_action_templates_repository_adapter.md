# Phase 4AH Action Templates Repository Adapter

## Status

Phase 4AH implements the action-templates repository adapter behind explicit flags only.

- Production repository adapter implementation behind explicit flag.
- Default backend remains fixture.
- No production route owner switch.
- No `production_compat` change.
- Legacy fallback retained.
- No external calls.
- No automation execution.
- No production owner enablement.
- `delete_ready`: false.

Current production behavior remains legacy `production_compat` fallback / `legacy_forward`. This PR does not change production ownership.

## Backend Flags

Future SQLAlchemy adapter use requires both:

- `AICRM_ACTION_TEMPLATES_REPO_BACKEND=sqlalchemy`.
- `AICRM_ACTION_TEMPLATES_DATABASE_URL`.

Rules:

- Default backend is fixture/local.
- Generic `DATABASE_URL` fallback is not allowed.
- Test/staging DB fallback is not allowed.
- If SQLAlchemy backend is requested without `AICRM_ACTION_TEMPLATES_DATABASE_URL`, the application returns degraded `production_repository_not_enabled` / production unavailable evidence.
- Production fixture success remains blocked.

## Table Mapping

Main table: `automation_operation_templates`.

- `id` -> `id` / `template_id`.
- `template_code` -> `code` / `template_code`.
- `template_name` -> `name` / `template_name`.
- `template_source` -> `template_source`.
- `category` -> `category`.
- `description` -> `description`.
- `status` -> `status`.
- `default_config_json` -> `default_config`.
- `ui_schema_json` -> `ui_schema`.
- `workflow_blueprint_json` -> `workflow_blueprint`.
- `node_blueprints_json` -> `node_blueprints`.
- `created_by` -> `created_by`.
- `updated_by` -> `updated_by`.
- `created_at` -> `created_at`.
- `updated_at` -> `updated_at`.
- `archived_at` -> `archived_at`.

Idempotency table: `automation_operation_template_idempotency`.

- `route_family`.
- `operation`.
- `operator`.
- `idempotency_key`.
- `request_hash`.
- `response_snapshot`.
- `resource_type`.
- `resource_id`.
- `status`.
- `created_at`.
- `updated_at`.

Audit table: `automation_operation_template_audit_log`.

- `route_family`.
- `operation`.
- `operator`.
- `resource_type`.
- `resource_id`.
- `before_snapshot`.
- `after_snapshot`.
- `request_payload`.
- `validation_result`.
- `rollback_payload`.
- `side_effect_safety`.
- `created_at`.

## Implemented Methods

Implemented adapter methods:

- `list_action_templates(filters)`.
- `create_action_template(payload, idempotency_key, operator)`.
- `list_action_template_audit_events(filters)`.

Excluded methods:

- `generate_action_template`.
- `create_action_template_from_workflow`.
- `update_action_template`.
- `delete_action_template`.
- `execute_action_template`.
- `send_action_template`.

## Idempotency Behavior

For create:

- Same `route_family + operation + operator + idempotency_key` and same `request_hash` replays `response_snapshot`.
- Same key with different `request_hash` returns conflict.
- Transaction is required.
- No partial writes are allowed.
- `response_snapshot` is stored after successful create.

## Audit / Rollback Behavior

For create:

- Audit event is required.
- `before_snapshot` is `{}`.
- `after_snapshot` is the created template projection.
- `request_payload` stores the validated safe payload.
- `validation_result` records validation success.
- `rollback_payload` is sufficient to archive/revert later in an approved phase.
- `side_effect_safety` records all real side effects as false.

## Production Guard

- Production path remains legacy fallback.
- This PR does not modify route ordering.
- This PR does not modify `aicrm_next/main.py`.
- This PR does not modify `aicrm_next/production_compat/api.py`.
- If the Next route is reached in production with fixture backend, successful fixture POST remains blocked.
- Adapter is not active for production traffic by default.

## Side-Effect Safety

Adapter responses include or preserve evidence that these are false:

- real external call.
- real automation execution.
- real outbound send.
- real WeCom call.
- real OpenClaw call.
- real MCP call.
- real LLM call.

## Future Parity / Smoke Requirements

Before any production owner change:

- local test DB parity harness.
- adapter integration smoke.
- staging smoke planning/evidence.
- production read-only dry-run.
- separate owner approval for production route ownership switch.

## Business Continuity

本 PR 只实现 action-templates production repository adapter behind explicit flag，不连接生产数据，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。production path 仍由 legacy fallback 保持；adapter 默认不接生产流量。

## Phase 4AI Recommendation

Recommended next step:

- `local_test_db_parity_harness_or_adapter_integration_smoke`

Phase 4AI can add local test DB parity harness / adapter integration smoke. It must not switch production owner, enable external calls, remove fallback, or authorize production write canary.
