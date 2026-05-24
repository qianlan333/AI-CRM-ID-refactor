# Phase 4AA Action Templates Implementation Plan

## Status

Phase 4AA is planning only for `/api/admin/automation-conversion/action-templates*`.

- Phase 4AA planning only.
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

No business route is added, removed, or modified. Current production behavior remains legacy `production_compat` fallback / `legacy_forward`.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Fallback/integration boundary:

- `aicrm_next.integration_gateway`

Planning route family:

- `/api/admin/automation-conversion/action-templates*`

This plan does not include run-due, execution, send, OpenClaw, WeCom, MCP, timer, workflow activation, customer pool state changes, agent runtime execution, fallback removal, or production_compat narrowing.

## Legacy Discovery

### Route Registration

| Method | Path | Handler | File | Planning action |
| --- | --- | --- | --- | --- |
| GET | `/api/admin/automation-conversion/action-templates` | `api_admin_automation_conversion_action_templates` | `wecom_ability_service/http/automation_conversion.py` | list action templates |
| POST | `/api/admin/automation-conversion/action-templates` | `api_admin_automation_conversion_action_templates` | `wecom_ability_service/http/automation_conversion.py` | create CRM-local action template |
| POST | `/api/admin/automation-conversion/action-templates/generate` | `api_admin_automation_conversion_action_template_generate` | `wecom_ability_service/http/automation_conversion.py` | out of scope because it can call the LLM adapter |
| POST | `/api/admin/automation-conversion/action-templates/from-workflow` | `api_admin_automation_conversion_action_template_from_workflow` | `wecom_ability_service/http/automation_conversion.py` | needs_legacy_confirmation before inclusion |

No registered detail, update, delete, options, or catalog action-template routes were found in the static route registration scan. `workflow_repo.update_operation_template_row` exists, but no HTTP action-template update route was found; treat update as `needs_legacy_confirmation`.

### Controller/API Functions

- list: `api_admin_automation_conversion_action_templates` with GET.
- create: `api_admin_automation_conversion_action_templates` with POST.
- detail: needs_legacy_confirmation; no route found.
- update: needs_legacy_confirmation; repository helper exists but no route found.
- delete: needs_legacy_confirmation; no route found.
- options/catalog: needs_legacy_confirmation; no route found.
- generate: out of scope because `generate_action_template` can call `call_deepseek_agent`.
- from-workflow: needs_legacy_confirmation because it reads workflow model state and derives template metadata.

### Service/Domain Functions

`list_action_templates` in `wecom_ability_service/domains/automation_conversion/action_template_service.py`:

- Read/write behavior: read-only. Merges builtin templates with `automation_operation_templates` rows.
- Validation behavior: rejects invalid `template_source`.
- Transaction behavior: no commit.
- Error shape: `ValueError` maps to `{"ok": false, "error": ...}` with HTTP 400.

`create_action_template` in `wecom_ability_service/domains/automation_conversion/action_template_service.py`:

- Read/write behavior: normalizes payload and inserts an `automation_operation_templates` row.
- Validation behavior: requires `template_name`; allows `template_source` only `crm_local` or `ai_generated`; allows `status` only `active` or `archived`; generates a unique `template_code`.
- Transaction behavior: `insert_operation_template_row` then `get_db().commit()`.
- Error shape: `ValueError` maps to HTTP 400.

`generate_action_template`:

- Out of scope for Phase 4AA planning because it calls `call_deepseek_agent`.
- It may insert a generated row after the external generation response, but external generation is not allowed in this candidate plan.

`create_action_template_from_workflow`:

- Needs legacy confirmation before inclusion.
- It requires `workflow_id` and `template_name`, reads a workflow model bundle, then inserts an `automation_operation_templates` row.

### Persistence

Confirmed table:

- `automation_operation_templates`

Schema sources:

- `wecom_ability_service/schema_postgres.sql`
- `wecom_ability_service/db/migrations/postgres_migrations.py`
- `wecom_ability_service/domains/automation_conversion/workflow_repo.py`

Visible fields:

- `id BIGSERIAL PRIMARY KEY`
- `template_code TEXT NOT NULL UNIQUE`
- `template_name TEXT NOT NULL DEFAULT ''`
- `template_source TEXT NOT NULL DEFAULT 'crm_local'`
- `category TEXT NOT NULL DEFAULT ''`
- `description TEXT NOT NULL DEFAULT ''`
- `status TEXT NOT NULL DEFAULT 'active'`
- `default_config_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `ui_schema_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `workflow_blueprint_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `node_blueprints_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `created_by TEXT NOT NULL DEFAULT ''`
- `updated_by TEXT NOT NULL DEFAULT ''`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP`
- `archived_at TIMESTAMPTZ`

Visible constraints/indexes:

- `template_code` unique.
- `template_source` check: `builtin`, `crm_local`, `ai_generated`.
- `status` check: `active`, `archived`.
- `idx_automation_operation_templates_source` on `(template_source, status, updated_at DESC, id DESC)`.
- `idx_automation_operation_templates_category` on `(category, status, updated_at DESC, id DESC)`.

Unknowns:

- No separate action-template idempotency/audit tables are visible.
- No exposed update/delete route is visible.
- Category allowed values are not visible as a schema constraint.

## Route Scope

In planning scope:

- Action template list/read.
- Action template create if bounded CRM-local metadata write remains confirmed.
- Action template detail only if a later phase confirms an exposed legacy route.
- Action template update only if a later phase confirms an exposed legacy route.
- Options/catalog only if a later phase confirms an exposed legacy route.

Out of scope:

- run-due.
- automation execution.
- outbound send.
- WeCom.
- OpenClaw.
- MCP.
- timer.
- workflow activation.
- customer pool state change.
- agent runtime execution.
- fallback removal.
- production_compat narrowing.
- AI generation / DeepSeek-backed `generate`.

## Native Contract Proposal

Tentative fields:

| Next field | Legacy field | Direction | Validation | Default | Status / unknowns |
| --- | --- | --- | --- | --- | --- |
| `id` | `id` | read | integer identifier | none | documented |
| `code` | `template_code` | read/write | unique slug; duplicate protection required | slugified name | documented |
| `name` | `template_name` | read/write | required non-empty text | none | documented |
| `template_source` | `template_source` | read/write | `crm_local` or `ai_generated`; builtin read-only | `crm_local` | documented |
| `category` | `category` | read/write | category enum needs owner confirmation | empty string | needs_legacy_confirmation |
| `description` | `description` | read/write | bounded text length to define | empty string | documented |
| `status` | `status` | read/write | `active` or `archived` | `active` | documented |
| `default_config` | `default_config_json` | read/write | JSON object; dangerous fields rejected | `{}` | documented |
| `ui_schema` | `ui_schema_json` | read/write | JSON object, UI-only metadata | `{}` | documented |
| `workflow_blueprint` | `workflow_blueprint_json` | read/write | JSON object; must not authorize activation/execution | `{}` | documented |
| `node_blueprints` | `node_blueprints_json` | read/write | JSON list; must not authorize sends/execution | `[]` | documented |
| `created_by` | `created_by` | read | operator identity required on create | operator id | documented |
| `updated_by` | `updated_by` | read | operator identity required on update if later confirmed | operator id | documented |
| `created_at` | `created_at` | read | server timestamp | current timestamp | documented |
| `updated_at` | `updated_at` | read | server timestamp | current timestamp | documented |

Do not invent unconfirmed detail/update/delete/options behavior. Mark those surfaces `needs_legacy_confirmation` until a later phase confirms them.

## Internal Write Guardrails

Future implementation must require:

- Idempotency for create if create remains in scope.
- Duplicate protection for name/code/action_key equivalents.
- Audit/operator identity.
- Before/after snapshot for update if update is later confirmed.
- Rollback payload.
- Validation that rejects dangerous fields:
  - `run_due`
  - `execute`
  - `send`
  - `wecom`
  - `openclaw`
  - `mcp`
  - `timer`
  - `workflow_activation`
  - `customer_pool_state_change`
  - `outbound_task`
- No external calls.
- No automation execution.
- Fallback retained.
- Checker and smoke coverage before any production use.

## Repository / Schema Strategy

Options:

- Reuse legacy tables: preferred only if schema confirmation is complete. It matches the visible table and current payload shape, but idempotency/audit may need companion planning.
- Legacy service adapter: transitional only. It preserves validation but risks carrying legacy internals and external-generation branches into Next.
- New Next-owned tables: not recommended without separate approval. It adds migration, dual-write, and cutover complexity.

Conservative recommendation:

- Select `reuse_legacy_tables_after_schema_confirmation`.
- Phase 4AB should perform schema confirmation only before any native fixture/local implementation.
- Do not recommend a migration unless schema confirmation proves it necessary and a later PR explicitly approves it.

## Business Continuity

本 PR 只生成 Phase 4AA action-templates implementation/native contract planning，不连接生产数据，不写生产，不实现 runtime，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。

## Risk / Rollback

Rollback is deleting the Phase 4AA document, YAML, checker, and test, plus any narrow checker allowlist maintenance. Runtime behavior, production data, route ownership, fallback behavior, `production_compat`, schema, and migrations are unchanged.

## Phase 4AB Recommendation

Recommended next step: schema confirmation only.

Phase 4AB should confirm action-template schema, route surface, category/source/status semantics, and whether update/detail/options exist. It must not switch production route owner, remove fallback, execute production writes, or enable external calls.
