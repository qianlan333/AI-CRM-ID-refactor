# Phase 4AG Action Templates Repository Adapter Plan

## Status

Phase 4AG is production repository adapter planning only for `/api/admin/automation-conversion/action-templates*`.

- No runtime implementation.
- No production DB connection.
- No production route owner switch.
- No `production_compat` change.
- Legacy fallback retained.
- No external calls.
- No automation execution.
- `delete_ready`: false.

Current production behavior remains legacy `production_compat` fallback / `legacy_forward`. This PR does not change production ownership.

## Repository Adapter Target

Future adapter target:

- `SqlAlchemyActionTemplateRepository`.
- Behind explicit backend flag only.
- Default backend remains fixture/local.

The future adapter must map:

- `automation_operation_templates`.
- `automation_operation_template_idempotency`.
- `automation_operation_template_audit_log`.

The adapter must not fall back to fixture/local success in production. If it is selected without required production configuration, it must return degraded `production_unavailable` / `production_repository_not_enabled` evidence.

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

## Adapter Methods

Planned methods:

- `list_action_templates(filters)`: read-only metadata list.
- `create_action_template(payload, idempotency_key, operator)`: bounded CRM-local metadata create with idempotency, audit, rollback payload, and transaction boundaries.
- `list_action_template_audit_events(filters)`: read-only audit evidence list.

Not planned:

- `generate_action_template`.
- `create_action_template_from_workflow`.
- `update_action_template` unless later route confirmation exists.
- `delete_action_template`.
- `execute_action_template`.
- `send_action_template`.

## Enablement Strategy

Future explicit opt-in flags:

- `AICRM_ACTION_TEMPLATES_REPO_BACKEND=sqlalchemy`.
- `AICRM_ACTION_TEMPLATES_DATABASE_URL`.

Requirements:

- Default remains fixture/local.
- Production fixture success remains blocked.
- If `backend=sqlalchemy` but DB config is missing, return degraded / production unavailable.
- Production route owner remains legacy fallback until a separate owner-switch PR.
- No generic `DATABASE_URL` fallback unless explicitly approved later.
- Any `production_compat` change requires a separate PR.

## Idempotency Strategy

For create:

- Same `route_family + operation + operator + idempotency_key` and same `request_hash` replays `response_snapshot`.
- Same key with different `request_hash` returns conflict.
- Transaction is required.
- No partial writes are allowed.

## Audit / Rollback Strategy

- Insert audit event on create.
- `before_snapshot` is an empty object for create.
- `after_snapshot` stores the full created template projection.
- `rollback_payload` must be sufficient to archive/revert later in an approved phase.
- `side_effect_safety` must show all real external side effects are false.

## Parity / Smoke Readiness

Future gates:

- Local test DB harness.
- Staging smoke package.
- Production read-only dry-run.
- Production write dry-run only later and separately approved.
- Route owner switch only later and separately approved.

Fixture/local evidence from Phase 4AF is not production evidence. It only proves local contract stability before repository adapter work.

## Business Continuity

本 PR 只生成 action-templates production repository adapter planning，不连接生产数据，不写生产，不实现 repository adapter，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。production path 仍由 legacy fallback 保持。

## Phase 4AH Recommendation

Recommended next step:

- `production_repository_adapter_implementation_behind_explicit_flag`

Phase 4AH may implement the action-templates repository adapter behind explicit flags. It must not switch production owner, enable external calls, remove fallback, or authorize production write canary.
