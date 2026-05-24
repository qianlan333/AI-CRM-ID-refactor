# Phase 4E Profile Segment Template Repository Adapter Plan

Status: Phase 4E planning/discovery only. This PR does not change runtime, implement a production repository, add a migration, change DB schema, change `production_compat`, switch production owner, remove fallback, enable real external calls, mark `delete_ready`, or authorize production cutover.

## Scope

Planning/discovery scope:

- `GET /api/admin/automation-conversion/profile-segment-templates/catalog`
- `GET /api/admin/automation-conversion/profile-segment-templates`
- `GET /api/admin/automation-conversion/profile-segment-templates/options`
- `GET /api/admin/automation-conversion/profile-segment-templates/{template_id}`
- `POST /api/admin/automation-conversion/profile-segment-templates`
- `PUT /api/admin/automation-conversion/profile-segment-templates/{template_id}`

Out of scope: delete, production repository implementation, migration, production route ownership switch, `production_compat` change, fallback removal, real external calls, run-due, automation execution, outbound send, WeCom, OpenClaw, MCP, timer, workflow activation, customer pool state change, and production cutover.

## Legacy Schema / Service Discovery

### Route Registration

| Method | Path | Handler | File |
| --- | --- | --- | --- |
| GET | `/api/admin/automation-conversion/profile-segment-templates/catalog` | `api_admin_automation_conversion_profile_segment_catalog` | `wecom_ability_service/http/automation_conversion.py` |
| GET | `/api/admin/automation-conversion/profile-segment-templates` | `api_admin_automation_conversion_profile_segment_templates` | `wecom_ability_service/http/automation_conversion.py` |
| GET | `/api/admin/automation-conversion/profile-segment-templates/options` | `api_admin_automation_conversion_profile_segment_template_options` | `wecom_ability_service/http/automation_conversion.py` |
| GET | `/api/admin/automation-conversion/profile-segment-templates/<int:template_id>` | `api_admin_automation_conversion_profile_segment_template_detail` | `wecom_ability_service/http/automation_conversion.py` |
| POST | `/api/admin/automation-conversion/profile-segment-templates` | `api_admin_automation_conversion_profile_segment_template_create` | `wecom_ability_service/http/automation_conversion.py` |
| PUT | `/api/admin/automation-conversion/profile-segment-templates/<int:template_id>` | `api_admin_automation_conversion_profile_segment_template_update` | `wecom_ability_service/http/automation_conversion.py` |

### Controller / API Functions

`wecom_ability_service/http/automation_conversion_templates.py` owns the legacy HTTP handlers:

- `api_admin_automation_conversion_profile_segment_catalog`: returns `{ ok: true, ...catalog }`.
- `api_admin_automation_conversion_profile_segment_templates`: parses `enabled_only` and `program_id`, returns list payload.
- `api_admin_automation_conversion_profile_segment_template_options`: parses `enabled_only` and `program_id`, returns selector options.
- `api_admin_automation_conversion_profile_segment_template_detail`: returns bundle or `404 { ok: false, error }` for missing/program mismatch.
- `api_admin_automation_conversion_profile_segment_template_create`: reads JSON, passes operator/program, returns `201 { ok: true, template_bundle }`, maps `ValueError` to 400 and `LookupError` to 404.
- `api_admin_automation_conversion_profile_segment_template_update`: reads JSON, passes operator/program, returns `{ ok: true, template_bundle }`, maps `ValueError` to 400 and `LookupError` to 404.

### Service / Domain Functions

`wecom_ability_service/domains/automation_conversion/workflow_service.py` owns the domain behavior:

- `list_conversion_profile_segment_catalog`: reads questionnaires, questions, and options for catalog payload.
- `list_conversion_profile_segment_templates`: reads template rows and builds template bundles.
- `list_conversion_profile_segment_template_options`: reads enabled valid bundles for selector options.
- `get_conversion_profile_segment_template_bundle`: reads one bundle or raises `LookupError`.
- `create_conversion_profile_segment_template`: validates template name/code/question/category state, inserts template/category/mapping rows, commits, returns bundle.
- `update_conversion_profile_segment_template`: loads existing row, checks program ownership, validates next state, updates template row, replaces category/mapping rows, commits, returns bundle.

Validation behavior observed statically:

- Create requires `template_name`, unique `template_code`, `questionnaire_id`, `segmentation_question_id`, at least one category, at least one enabled category, enabled categories with option bindings, and valid segmentation question/category mapping.
- Update preserves omitted fields, validates program ownership, rejects duplicate `template_code`, validates enabled state, increments `version` when the state fingerprint changes, and rebuilds child rows.
- Error shape is `{ ok: false, error }` with 400 for validation and 404 for not found.

### Persistence Layer

`wecom_ability_service/domains/automation_conversion/_workflow_repo_profile_segment.py` performs direct SQL through `get_db()` helpers.

Tables from `wecom_ability_service/schema_postgres.sql`:

- `automation_profile_segment_template`: `id`, `program_id`, `template_code`, `template_name`, `questionnaire_id`, `segmentation_question_id`, `description`, `enabled`, `version`, `created_by`, `updated_by`, `created_at`, `updated_at`.
- `automation_profile_segment_category`: `id`, `template_id`, `category_key`, `category_name`, `description`, `sort_order`, `enabled`, `created_at`, `updated_at`.
- `automation_profile_segment_option_mapping`: `id`, `template_id`, `category_id`, `question_id`, `option_id`, `created_at`.

Indexes / constraints discovered:

- `automation_profile_segment_template.template_code` is unique.
- `idx_automation_profile_segment_template_enabled` supports enabled list ordering.
- `idx_automation_profile_segment_template_program` supports program-scoped enabled list ordering.
- `uq_automation_profile_segment_category_template_key` makes category key unique per template.
- `uq_automation_profile_segment_option_mapping_unique` makes option mapping unique per category/question/option.

Unknowns:

- No idempotency key column/table was found in the profile segment schema.
- A dedicated profile segment audit table was not confirmed.
- Exact production operator identity source for a Next adapter requires owner confirmation.
- Safe namespace or dry-run mechanics for production smoke require owner confirmation.

## Field Mapping

| Next field | Legacy field/table | Direction | Required | Transform | Default behavior | Unknowns / risk |
| --- | --- | --- | --- | --- | --- | --- |
| `template_id` / `id` | `automation_profile_segment_template.id` | read/write identity | yes | integer identity mapping | DB generated on create | none |
| `name` | `automation_profile_segment_template.template_name` | both | yes | alias `name` to `template_name` | create rejects empty | length limit needs owner confirmation |
| `description` | `automation_profile_segment_template.description` | both | no | empty string normalization | empty string | length limit needs owner confirmation |
| `segment_key` / `code` | `automation_profile_segment_template.template_code` | both | yes | slug/code alias to `template_code` | legacy slugifies from name when omitted | collision behavior must match legacy duplicate error |
| `conditions` / `rules` | category rows plus option mappings | both | yes | map JSON contract to categories and option ids | enabled template requires enabled category with mappings | exact Next alias compatibility needs parity fixture |
| `status` | `automation_profile_segment_template.enabled` | both | yes | map draft/active/inactive to enabled/status view | legacy exposes enabled/disabled | draft has no native legacy column; owner approval needed |
| `sort_order` | `automation_profile_segment_category.sort_order` | both | no | category-level only | category index order | no template-level sort_order found |
| `created_at` | `automation_profile_segment_template.created_at` | read | yes | timestamp projection | DB default current timestamp | timezone normalization needs parity check |
| `updated_at` | `automation_profile_segment_template.updated_at` | read | yes | timestamp projection | DB updates current timestamp | timezone normalization needs parity check |
| `operator` / audit | `created_by`, `updated_by` | write | yes | operator identity snapshot | legacy `_operator_from_request` | dedicated audit storage not confirmed |

## Repository Adapter Strategy

### Option A: `SqlAlchemyProfileSegmentTemplateRepository` reuses existing legacy tables

Pros:

- Preserves current production source of truth.
- Avoids data copy, backfill, and dual-source drift.
- Keeps rollback to `production_compat` straightforward.

Cons:

- Requires faithful legacy bundle projection.
- Idempotency and audit requirements may need companion schema planning.
- Update currently deletes/reinserts child rows, so rollback needs before snapshots.

Operational risk: moderate and manageable after schema confirmation.
Rollback complexity: lowest of the three options.
Parity complexity: requires bundle-level comparison but avoids cross-store comparison.

Recommendation: preferred after production schema confirmation and owner approval.

### Option B: repository adapter calls legacy service/domain functions from integration boundary

Pros:

- Fastest behavior parity with current legacy code.
- Avoids re-implementing validation during discovery.

Cons:

- Couples Next repository to legacy service internals.
- Risks expanding legacy dependency instead of replacing it.
- Harder to test outside legacy runtime.

Operational risk: medium; useful only as a temporary integration bridge.
Rollback complexity: low, but architectural replacement value is weak.
Parity complexity: low behavior gap, high boundary risk.

Recommendation: defer except as a short-lived integration_gateway bridge if owner explicitly chooses it.

### Option C: new Next-owned tables + migration

Pros:

- Can model idempotency, audit, and rollback natively.
- Can isolate the Next-owned contract.

Cons:

- Requires migration, backfill, and synchronization strategy.
- Introduces dual-source drift risk.
- Complicates fallback rollback if writes land in a separate store.

Operational risk: highest.
Rollback complexity: highest.
Parity complexity: highest.

Recommendation: defer until reuse is proven impossible and a separate schema/migration plan is approved.

Recommended strategy for Phase 4F planning: schema confirmation only, then reuse existing legacy tables through a narrow production repository adapter if owner approves.

## Planned Production Repository Contract

Future interface only; not implemented in this PR:

| Method | Read/write | Transaction | Idempotency | Audit | Rollback | Validation boundary | Error behavior |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `list_profile_segment_templates(filters, limit, offset)` | read | no | no | no | no | filter/pagination normalization | degraded `production_unavailable` if repository unavailable |
| `get_profile_segment_template(template_id)` | read | no | no | no | no | template id normalization | 404 not found; degraded if unavailable |
| `create_profile_segment_template(payload, idempotency_key, operator)` | write | yes | yes | yes | yes | Next command validation plus legacy parity validation before insert | 400 validation, 409 conflict, degraded if unavailable |
| `update_profile_segment_template(template_id, patch, operator)` | write | yes | optional key/version guard | yes | yes | Next patch validation plus legacy parity validation before update | 404 missing, 400 validation, 409 stale/conflict, degraded if unavailable |
| `list_catalog()` | read | no | no | no | no | questionnaire catalog projection | degraded if unavailable |
| `list_options(filters)` | read | no | no | no | no | `enabled_only`/`program_id` normalization | degraded if unavailable |

## Idempotency Design

Create requires production idempotency.

- Key source: explicit request idempotency key header/body field from admin client or server-generated operation id approved by owner.
- Key scope: route family + operator + idempotency key.
- Replay behavior: same key returns original create result without inserting duplicate rows.
- Duplicate behavior: duplicate template name/code with a different key returns conflict.
- Conflict response: 409 with a stable error code in the future implementation.
- Retry safety: repository must execute in one transaction and persist idempotency before or with the created template.

Storage status: no idempotency column/table found in current profile segment schema. Phase 4F must either confirm an existing shared idempotency store or stop at schema/migration planning.

## Audit / Operator Identity Design

Audit is required for production writes.

- Operator source: authenticated admin identity equivalent to legacy `_operator_from_request`.
- Fallback if missing: reject write or use an explicit system operator only with owner approval; do not silently write anonymous production changes.
- Audit event shape: `{ action, route_family, template_id, operator_id, idempotency_key, before, after, created_at }`.
- Snapshot requirement: create stores after snapshot; update stores before and after snapshots.
- Storage status: `created_by` and `updated_by` fields exist, but dedicated before/after audit storage is not confirmed.

## Rollback / Data Recovery Design

- Create rollback: capture created template id and either disable/revert fields through compensating update or delete only if separately approved.
- Update rollback: restore before snapshot through compensating update.
- Stale update handling: require `version`, `updated_at`, etag, or equivalent owner-approved guard before production writes.
- Backup/snapshot: required before any DB write implementation or smoke.
- Fallback route rollback: keep or restore `production_compat` owner; disable future feature flag if introduced.

## Parity Test Design

Required parity fixtures/checks:

- static contract parity between Phase 4C Next projection and legacy bundle shape
- read parity for list/detail/catalog/options
- validation parity for missing/invalid template fields and category mappings
- create dry-run or shadow parity without production writes
- update dry-run or shadow parity without production writes
- error shape parity for 400, 404, and future 409 conflicts
- audit/rollback parity for before/after snapshot requirements

Write paths must not dual-write production in Phase 4E.

## Phase 4F Recommendation

Recommended next step: schema confirmation only.

Phase 4F should confirm production schema, idempotency storage, audit storage, and operator identity before implementing a production repository adapter. If those are confirmed sufficient, a later PR may implement the repository adapter behind no route owner switch. If idempotency/audit storage is missing, the next PR should be schema/migration planning only.

Do not switch production route owner in Phase 4F.
