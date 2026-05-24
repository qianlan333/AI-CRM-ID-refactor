# Phase 4F Profile Segment Template Schema Confirmation

Status: Phase 4F schema confirmation only. This PR does not change runtime, implement a production repository, add migration, change DB schema, change `production_compat`, switch production owner, remove fallback, enable real external calls, mark `delete_ready`, or authorize production cutover.

## Scope

Schema confirmation scope:

- `GET /api/admin/automation-conversion/profile-segment-templates/catalog`
- `GET /api/admin/automation-conversion/profile-segment-templates`
- `GET /api/admin/automation-conversion/profile-segment-templates/options`
- `GET /api/admin/automation-conversion/profile-segment-templates/{template_id}`
- `POST /api/admin/automation-conversion/profile-segment-templates`
- `PUT /api/admin/automation-conversion/profile-segment-templates/{template_id}`

Out of scope: production repository implementation, migration, production route owner switch, `production_compat` change, fallback removal, DB schema change, delete route, run-due, automation execution, outbound send, WeCom, OpenClaw, MCP, timer, workflow activation, customer pool state change, and production cutover.

## Confirmed Legacy Table Definitions

Static source: `wecom_ability_service/schema_postgres.sql`. Older-database compatibility source: `wecom_ability_service/db/migrations/postgres_migrations.py`, which adds `program_id`, `segmentation_question_id`, and program index for older stores.

| Table | Primary key | Required/default fields | Constraints / indexes | Timestamp handling | Status semantics | Unknowns |
| --- | --- | --- | --- | --- | --- | --- |
| `automation_profile_segment_template` | `id BIGSERIAL PRIMARY KEY` | `template_code`, `template_name`, `description`, `enabled`, `version`, `created_by`, `updated_by`, `created_at`, `updated_at`; defaults exist for name/description/operator snapshot, `enabled=true`, `version=1`, timestamps current | unique `template_code`; indexes on `(enabled, updated_at, id)` and `(program_id, enabled, updated_at, id)` | create defaults both timestamps; update SQL sets `updated_at = CURRENT_TIMESTAMP` | `enabled` is the only native status flag; `version` increments on changed state | no idempotency key, no before/after audit snapshot, no native draft column |
| `automation_profile_segment_category` | `id BIGSERIAL PRIMARY KEY` | `template_id`, `category_key`, `category_name`, `description`, `sort_order`, `enabled`, timestamps; defaults for text, sort, enabled, timestamps | FK to template; unique `(template_id, category_key)`; index `(template_id, sort_order, id)` | create defaults timestamps; update flow deletes and reinserts rows | category-level `enabled` flag | update rollback requires old category snapshot because rows are replaced |
| `automation_profile_segment_option_mapping` | `id BIGSERIAL PRIMARY KEY` | `template_id`, `category_id`, `question_id`, `option_id`, `created_at` | FKs to template/category/question/option; unique `(category_id, question_id, option_id)`; index `(template_id, question_id, option_id, id)` | create defaults `created_at`; update flow deletes and reinserts rows | no status flag | update rollback requires old mapping snapshot because rows are replaced |

## Confirmed Legacy Service Behavior

| Function | File | Read/write behavior | Validation behavior | Transaction / commit | Error behavior | Operator handling | Rollback implications | Unknowns |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `list_conversion_profile_segment_catalog` | `wecom_ability_service/domains/automation_conversion/workflow_service.py` | reads questionnaires, questions, and options | read normalization only | no commit | DB errors bubble | none | none | future Next error wrapping still required |
| `list_conversion_profile_segment_templates` | same | reads template rows, builds bundle payloads | enabled/program filter normalization | no commit | DB errors bubble | none | none | payload parity fixture required |
| `list_conversion_profile_segment_template_options` | same | reads bundles and returns selector options | filters invalid bundles when `enabled_only` is true | no commit | DB errors bubble | none | none | invalid-template filtering needs parity fixture |
| `get_conversion_profile_segment_template_bundle` | same | reads one template and expands questionnaire/category/mapping metadata | missing row is invalid | no commit | raises `LookupError` for missing | none | none | projection differences must be locked before adapter |
| `create_conversion_profile_segment_template` | same | inserts template, category, and option mapping rows | requires `template_name`, unique code, questionnaire/question ids, categories, enabled category, option bindings, valid question/options | calls `get_db().commit()` after parent/child inserts | `ValueError` for validation/duplicate; `LookupError` may surface from lookup validation | writes `created_by` and `updated_by` | rollback needs created template id and child rows; retry safety needs idempotency storage | no robust idempotency storage or before/after audit confirmed |
| `update_conversion_profile_segment_template` | same | updates parent, deletes/reinserts category and mapping rows | requires existing row, program match, non-empty name, unique code, valid enabled category mappings and question | calls `get_db().commit()` after parent update and child replacement | `LookupError` for missing; `ValueError` for validation/program mismatch/duplicate | writes `updated_by` | rollback needs before snapshot of parent/categories/mappings | no full audit snapshot; version increments but is not an explicit optimistic lock |

Legacy HTTP handlers in `wecom_ability_service/http/automation_conversion_templates.py` map `ValueError` to 400 and `LookupError` to 404. They use `_operator_from_request()` for create/update operator snapshots.

## Field Mapping Confirmation

| Next field | Legacy field/table | Status | Notes |
| --- | --- | --- | --- |
| `template_id / id` | `automation_profile_segment_template.id` | confirmed | Direct integer identity. |
| `name` | `automation_profile_segment_template.template_name` | confirmed | Legacy create/update require non-empty `template_name`. |
| `description` | `automation_profile_segment_template.description` | confirmed | Legacy normalizes omitted value to empty string. |
| `segment_key / code` | `automation_profile_segment_template.template_code` | confirmed | Legacy slugifies missing code from name and enforces unique `template_code`. |
| `conditions / rules` | categories plus option mappings | needs_owner_approval | Legacy payload is category/option based; Next aliases need parity fixture approval before production adapter. |
| `status` | `automation_profile_segment_template.enabled` | needs_owner_approval | Legacy supports enabled/disabled; draft has no native legacy status column. |
| `sort_order` | `automation_profile_segment_category.sort_order` | confirmed | Confirmed at category level only; no template-level sort column. |
| `created_at` | `automation_profile_segment_template.created_at` | confirmed | DB default and serializer projection exist. |
| `updated_at` | `automation_profile_segment_template.updated_at` | confirmed | DB default and update SQL refresh exist. |
| `operator / audit fields` | `created_by` / `updated_by` | needs_migration | Operator snapshot exists, but complete audit event and before/after snapshot storage are not confirmed. |

## Idempotency Confirmation

Existing profile segment tables do not appear to provide dedicated idempotency storage. Static scan confirmed duplicate protection through `template_code`, but that is not equivalent to replay-safe create idempotency.

Phase 4G cannot implement production create with robust idempotency unless one of these is chosen:

- companion idempotency table
- approved shared request log reuse
- deterministic duplicate protection only, explicitly weaker and owner-approved

Recommended path: plan companion idempotency/audit schema or approved shared storage before any production create adapter.

## Audit Confirmation

`created_by` and `updated_by` exist as operator snapshots on `automation_profile_segment_template`. Dedicated profile-segment audit event storage and before/after snapshot storage were not confirmed in the profile segment schema.

The global `admin_operation_logs` table exists, but this PR does not confirm a wired profile-segment integration. Phase 4G cannot claim full audit unless audit storage is confirmed or a companion audit design is approved.

Recommended path: define an approved audit sink with `{ action, route_family, template_id, operator, before, after, idempotency_key, created_at }` before production writes.

## Repository Adapter Feasibility Decision

Decision: `reuse_legacy_tables_needs_companion_idempotency_audit`.

The existing legacy tables appear sufficient for read parity and the basic metadata persistence shape for create/update. They are not sufficient for robust production internal_write guardrails because idempotency storage and before/after audit snapshots are not confirmed.

Therefore:

- production adapter implementation is not allowed next by this PR
- migration or companion schema planning is required before adapter implementation unless owner explicitly approves an existing shared mechanism
- owner approval remains required
- route owner switch remains forbidden

## Phase 4G Recommendation

Recommended Phase 4G next step: companion idempotency/audit schema planning.

Phase 4G may also be limited to production repository adapter planning if owners provide an approved existing idempotency/audit mechanism before the PR starts. It must not directly switch production route owner, implement production writes without owner approval, remove fallback, or narrow `production_compat`.
