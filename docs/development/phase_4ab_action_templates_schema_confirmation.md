# Phase 4AB Action Templates Schema Confirmation

## Status

Phase 4AB is schema / route surface / service behavior confirmation only for `/api/admin/automation-conversion/action-templates*`.

- Phase 4AB schema confirmation only.
- No runtime change.
- No production repository.
- No migration.
- No production route owner switch.
- No `production_compat` change.
- Legacy fallback retained.
- No external calls.
- No automation execution.
- No outbound send.
- `delete_ready`: false.

Current production behavior remains legacy `production_compat` fallback / `legacy_forward`. This PR does not add, remove, or modify business routes.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Fallback/integration boundary:

- `aicrm_next.integration_gateway`

Route family under confirmation:

- `/api/admin/automation-conversion/action-templates*`

`generate_action_template`, DeepSeek, LLM adapter paths, WeCom, Payment, OAuth, OpenClaw, MCP, timer, automation execution, outbound send, media upload, workflow activation, and customer pool state changes remain out of scope.

## Route Surface Confirmation

Static route registration confirms:

| Method | Path | Handler | Phase 4AC decision | Reason |
| --- | --- | --- | --- | --- |
| GET | `/api/admin/automation-conversion/action-templates` | `api_admin_automation_conversion_action_templates` | in_scope | Read-only list route delegates to `list_action_templates`. |
| POST | `/api/admin/automation-conversion/action-templates` | `api_admin_automation_conversion_action_templates` | in_scope | Create route can remain bounded to CRM-local metadata writes if idempotency/audit/rollback guardrails are planned first. |
| POST | `/api/admin/automation-conversion/action-templates/generate` | `api_admin_automation_conversion_action_template_generate` | out_of_scope | Calls `generate_action_template`, which invokes `call_deepseek_agent`. |
| POST | `/api/admin/automation-conversion/action-templates/from-workflow` | `api_admin_automation_conversion_action_template_from_workflow` | defer | Reads workflow model state before inserting template metadata; boundedness needs a separate review. |

Not confirmed as HTTP routes:

- `GET /api/admin/automation-conversion/action-templates/{template_id}`
- `PUT /api/admin/automation-conversion/action-templates/{template_id}`
- `DELETE /api/admin/automation-conversion/action-templates/{template_id}`
- `GET /api/admin/automation-conversion/action-templates/options`
- `GET /api/admin/automation-conversion/action-templates/catalog`

`workflow_repo.update_operation_template_row` exists, but no action-template update route is registered. No delete route is registered; archive behavior exists only as `status=archived` semantics in the repository helper.

## Service Behavior Confirmation

`list_action_templates` in `wecom_ability_service/domains/automation_conversion/action_template_service.py`:

- Behavior: reads builtin templates and `automation_operation_templates` rows, then returns `items` and `total`.
- Validation: rejects invalid `template_source`; supports source, category, keyword, and include_archived filters.
- Transaction behavior: read-only, no commit.
- Error behavior: `ValueError` maps to HTTP 400.
- Side-effect risk: none / read-only.
- Phase 4AC decision: in_scope.

`create_action_template`:

- Behavior: normalizes payload, generates a unique `template_code`, inserts `automation_operation_templates`, and commits.
- Validation: requires `template_name`; restricts `template_source` to `crm_local` or `ai_generated`; restricts `status` to `active` or `archived`.
- Transaction behavior: `insert_operation_template_row` then `get_db().commit()`.
- Error behavior: `ValueError` maps to HTTP 400.
- Side-effect risk: bounded internal metadata write.
- Phase 4AC decision: in_scope only after companion idempotency/audit planning.

`generate_action_template`:

- Behavior: calls `call_deepseek_agent`, normalizes generated payload, inserts `automation_operation_templates`, and commits.
- Validation: requires `business_goal` and validates generated config/blueprints.
- Transaction behavior: insert then commit; rollback on generation failure.
- Error behavior: DeepSeek/client, lookup, validation, type, and JSON errors are wrapped as `ValueError`.
- Side-effect risk: external LLM call.
- Phase 4AC decision: out_of_scope.

`create_action_template_from_workflow`:

- Behavior: reads workflow model bundle, infers an action template, inserts `automation_operation_templates`, and commits.
- Validation: requires `workflow_id` and `template_name`.
- Transaction behavior: insert then `get_db().commit()`.
- Error behavior: `LookupError` maps to HTTP 404; `ValueError` maps to HTTP 400.
- Side-effect risk: workflow-state read plus metadata write.
- Phase 4AC decision: defer until boundedness is reviewed separately.

## Schema Confirmation

Confirmed table:

- `automation_operation_templates`

Schema sources:

- `wecom_ability_service/schema_postgres.sql`
- `wecom_ability_service/db/migrations/postgres_migrations.py`
- `wecom_ability_service/domains/automation_conversion/workflow_repo.py`

Primary key:

- `id BIGSERIAL PRIMARY KEY`

Fields:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | yes | primary key |
| `template_code` | TEXT | yes | unique action-template code |
| `template_name` | TEXT | yes | display name, required by create |
| `template_source` | TEXT | yes | `builtin`, `crm_local`, `ai_generated` |
| `category` | TEXT | yes | filter metadata; enum not constrained |
| `description` | TEXT | yes | descriptive metadata |
| `status` | TEXT | yes | `active`, `archived` |
| `default_config_json` | JSONB | yes | default action config |
| `ui_schema_json` | JSONB | yes | UI metadata |
| `workflow_blueprint_json` | JSONB | yes | workflow blueprint metadata only |
| `node_blueprints_json` | JSONB | yes | node blueprint metadata only |
| `created_by` | TEXT | yes | operator snapshot |
| `updated_by` | TEXT | yes | operator snapshot |
| `created_at` | TIMESTAMPTZ | yes | defaults to `CURRENT_TIMESTAMP` |
| `updated_at` | TIMESTAMPTZ | yes | defaults to `CURRENT_TIMESTAMP`; set by write helpers |
| `archived_at` | TIMESTAMPTZ | no | set by update helper when status becomes archived |

Constraints / indexes:

- Primary key on `id`.
- Unique key on `template_code`.
- `template_source` check: `builtin`, `crm_local`, `ai_generated`.
- `status` check: `active`, `archived`.
- `idx_automation_operation_templates_source` on `(template_source, status, updated_at DESC, id DESC)`.
- `idx_automation_operation_templates_category` on `(category, status, updated_at DESC, id DESC)`.

Timestamp behavior:

- `created_at` and `updated_at` default to `CURRENT_TIMESTAMP`.
- Insert helper sets both timestamps to `CURRENT_TIMESTAMP`.
- Update helper sets `updated_at` to `CURRENT_TIMESTAMP`.

Archive/status behavior:

- `status` is constrained to `active` or `archived`.
- Update helper sets `archived_at` when status becomes `archived` and `archived_at` is empty.
- No HTTP delete/archive route is confirmed for action templates.

Unknowns:

- No dedicated action-template idempotency table is visible.
- No dedicated action-template audit or before/after snapshot table is visible.
- Category allowed values are not constrained by schema.
- Detail, update, delete, options, and catalog HTTP routes are not confirmed.

## Field Mapping Confirmation

| Next field | Legacy field | Table | Status | Notes |
| --- | --- | --- | --- | --- |
| `id` | `id` | `automation_operation_templates` | confirmed | numeric primary key |
| `code` | `template_code` | `automation_operation_templates` | confirmed | unique code generated by service if omitted |
| `name` | `template_name` | `automation_operation_templates` | confirmed | required display name |
| `template_source` | `template_source` | `automation_operation_templates` | confirmed | builtin read-only; create accepts `crm_local` or `ai_generated` |
| `category` | `category` | `automation_operation_templates` | needs_owner_approval | field exists; taxonomy not constrained by schema |
| `description` | `description` | `automation_operation_templates` | confirmed | metadata text |
| `status` | `status` | `automation_operation_templates` | confirmed | active or archived |
| `default_config` | `default_config_json` | `automation_operation_templates` | confirmed | JSONB object |
| `ui_schema` | `ui_schema_json` | `automation_operation_templates` | confirmed | JSONB UI metadata |
| `workflow_blueprint` | `workflow_blueprint_json` | `automation_operation_templates` | confirmed | metadata, not execution authorization |
| `node_blueprints` | `node_blueprints_json` | `automation_operation_templates` | confirmed | metadata, not send/execution authorization |
| `created_by` | `created_by` | `automation_operation_templates` | confirmed | operator snapshot only |
| `updated_by` | `updated_by` | `automation_operation_templates` | confirmed | operator snapshot only |
| `created_at` | `created_at` | `automation_operation_templates` | confirmed | server timestamp |
| `updated_at` | `updated_at` | `automation_operation_templates` | confirmed | server timestamp |
| `archived_at` | `archived_at` | `automation_operation_templates` | confirmed | archive timestamp helper only |

## Idempotency / Audit Gap

- Dedicated idempotency storage for action templates: not confirmed.
- Dedicated audit storage for action templates: not confirmed.
- Dedicated before/after snapshot storage for action templates: not confirmed.
- `created_by` / `updated_by` are operator snapshots only.
- Companion schema may be needed before fixture/native contract implementation moves beyond planning.

## Phase 4AC Implementation Readiness Decision

Decision:

- `needs_companion_idempotency_audit_planning`

Reason:

- The legacy table is confirmed and list/create are confirmed route surfaces.
- However, create is an internal write and there is no visible dedicated idempotency/audit/before-after snapshot storage for action templates.
- `generate` remains excluded because it can trigger a real LLM path.
- `from-workflow` remains deferred because it derives metadata from workflow state and needs a separate boundedness review.

Required guardrails before implementation:

- Idempotency for create.
- Duplicate protection.
- Audit/operator identity.
- Rollback payload.
- Dangerous-field rejection.
- No real external side effect.
- No automation execution.
- Fallback retained.

## Business Continuity

本 PR 只生成 Phase 4AB action-templates schema/route/service confirmation，不连接生产数据，不写生产，不实现 runtime，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。

## Risk / Rollback

Rollback is deleting the Phase 4AB document, YAML, checker, and test, plus any narrow Phase 4AA checker allowlist maintenance. Runtime behavior, production data, route ownership, fallback behavior, `production_compat`, schema, and migrations are unchanged.

## Phase 4AC Recommendation

Recommended next step:

- `companion_idempotency_audit_planning`

Phase 4AC should plan companion idempotency/audit coverage before fixture/native contract implementation. It must not switch production owner, enable external calls, execute production writes, remove fallback, or modify `production_compat`.
