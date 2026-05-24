# Phase 4D Profile Segment Template Production Switch Plan

Status: Phase 4D planning only. This PR does not change runtime, implement a production repository, add a migration, change DB schema, change `production_compat`, switch production owner, remove fallback, enable real external calls, mark `delete_ready`, or authorize production cutover.

## Route Scope

Planning scope:

| Method | Route | Action |
| --- | --- | --- |
| GET | `/api/admin/automation-conversion/profile-segment-templates/catalog` | catalog read |
| GET | `/api/admin/automation-conversion/profile-segment-templates` | list templates |
| GET | `/api/admin/automation-conversion/profile-segment-templates/options` | list selector options |
| GET | `/api/admin/automation-conversion/profile-segment-templates/{template_id}` | template detail |
| POST | `/api/admin/automation-conversion/profile-segment-templates` | create bounded internal metadata template |
| PUT | `/api/admin/automation-conversion/profile-segment-templates/{template_id}` | update bounded internal metadata template |

Out of scope: delete, run-due, automation execution, outbound send, WeCom, OpenClaw, MCP, timer, workflow activation, customer pool state change, fallback removal, production cutover, and `production_compat` narrowing.

## Legacy Production Data Discovery

Static discovery from current legacy code:

| Concern | Current legacy location | Notes |
| --- | --- | --- |
| Route registration | `wecom_ability_service/http/automation_conversion.py` | Registers catalog, list, options, detail, create, and update. No Phase 4D route changes. |
| HTTP handlers | `wecom_ability_service/http/automation_conversion_templates.py` | Handlers return `{ ok: true, ... }`, 400 for `ValueError`, and 404 for `LookupError`. |
| Service functions | `wecom_ability_service/domains/automation_conversion/workflow_service.py` | Uses `list_conversion_profile_segment_catalog`, `list_conversion_profile_segment_templates`, `list_conversion_profile_segment_template_options`, `get_conversion_profile_segment_template_bundle`, `create_conversion_profile_segment_template`, and `update_conversion_profile_segment_template`. |
| DB access layer | `wecom_ability_service/domains/automation_conversion/_workflow_repo_profile_segment.py` | Reads/writes profile segment template, category, and option mapping rows. |
| Tables | `wecom_ability_service/schema_postgres.sql` | `automation_profile_segment_template`, `automation_profile_segment_category`, `automation_profile_segment_option_mapping`; references questionnaire tables. |
| Production fallback | `aicrm_next/production_compat/api.py` | Exact `/api/admin/automation-conversion/profile-segment-templates*` route family remains legacy-forwarded. |

Current payload fields observed in legacy:

- template: `id`, `program_id`, `template_code`, `template_name`, `questionnaire_id`, `segmentation_question_id`, `description`, `enabled`, `version`, `created_by`, `updated_by`, `created_at`, `updated_at`
- category: `id`, `template_id`, `category_key`, `category_name`, `description`, `sort_order`, `enabled`, timestamps
- option mapping: `id`, `template_id`, `category_id`, `question_id`, `option_id`, timestamp

Current create/update behavior:

- Create requires `template_name`, unique `template_code`, `questionnaire_id`, `segmentation_question_id`, at least one category, at least one enabled category, enabled categories with option bindings, and valid segmentation question/category mapping.
- Update loads the existing row, checks program ownership, preserves existing values when omitted, validates the next category/question state when enabled, increments `version` when the state fingerprint changes, replaces category/mapping rows, commits, and returns the rebuilt bundle.
- Current code records `created_by` and `updated_by`; a dedicated audit event table for this route family is not confirmed.
- Current idempotency-key storage is not confirmed. Duplicate protection exists through `template_code`; Phase 4E must not treat this as full idempotency without owner approval.
- Rollback today is possible through production fallback and compensating update from a captured before snapshot. Delete-based rollback is not approved by Phase 4D.

Unknowns that must be confirmed before implementation:

- Whether production already has all expected table columns and indexes from `schema_postgres.sql`.
- Whether any production-only validation or operator identity behavior differs from static code.
- Whether idempotency should use a new companion table, request log, or deterministic duplicate check.
- Whether audit evidence should reuse an existing audit/event table or require a new planning PR.
- What safe namespace, dry-run, or fixture-free production smoke data is approved.

## Production Repository Strategy

### Option A: Reuse existing legacy tables through a Next repository adapter

Pros:

- Avoids data copy and dual-source drift.
- Preserves the existing automation workspace production data shape.
- Keeps rollback simple: restore `production_compat` ownership or disable a future feature flag.
- Minimizes migration blast radius if the existing schema is sufficient.

Cons:

- Next adapter must faithfully reproduce legacy bundle shape and validation.
- Idempotency and audit requirements may exceed the current table shape.
- Legacy category update currently deletes/reinserts category and mapping rows, so rollback requires before snapshots.

Risks:

- Incomplete parity could break daily automation configuration pages.
- Schema assumptions must be verified against production before implementation.
- If idempotency/audit gaps need schema, Phase 4E must stop at schema/migration planning.

Recommendation: prefer this as the first production repository adapter strategy after schema discovery. It is the conservative option because it keeps the current production source of truth and reduces cutover risk.

### Option B: Add new Next-owned tables and migration

Pros:

- Can model idempotency, audit, rollback, and Next contract fields directly.
- Can isolate Next-owned API semantics from legacy table quirks.

Cons:

- Requires migration, backfill, parity, dual-source handling, and a more complex rollback.
- Adds production schema risk before route ownership is proven.
- Introduces potential drift between legacy and Next data.

Risks:

- Higher production continuity risk.
- Fallback becomes harder if writes land in a separate Next-owned store.
- Requires backup, migration smoke, and owner approval before any implementation.

Recommendation: defer unless schema discovery proves the legacy tables cannot safely support Phase 4E parity and guardrails.

Selected strategy for planning: reuse legacy tables through a Next repository adapter, pending owner approval and production schema discovery.

## Migration Strategy

No migration is included or authorized in Phase 4D.

Future sequencing:

1. Phase 4E may add or plan a repository adapter only if existing legacy tables are sufficient.
2. If idempotency, audit, or rollback requires new schema, Phase 4E must become schema/migration planning only or split into a separate migration PR.
3. No production schema change may proceed without production config review, backup/snapshot plan, rollback owner, migration smoke, and owner approval.

## Route Ownership Switch Strategy

Options:

- Option 1: Keep `production_compat` owner and run Next native only in fixture/staging. This remains the Phase 4D state.
- Option 2: Add feature-flagged exact Next owner for production read-only routes first after repository parity.
- Option 3: Add feature-flagged create/update only after idempotency, audit, rollback, and smoke are proven.
- Option 4: Narrow `production_compat` exact route only after sustained parity and fallback rollback are proven.

Final recommendation:

- Do not switch production owner in Phase 4D.
- Phase 4E should plan or implement production repository/parity only.
- Route ownership switch should be a separate Phase 4F or later PR, with legacy fallback retained.

## Dual-Run / Parity Plan

Required parity checks:

- list parity
- detail parity
- catalog/options parity
- create dry-run or shadow validation
- update dry-run or shadow validation
- payload shape comparison
- validation error comparison
- idempotency behavior comparison
- audit/rollback comparison

Write paths must not dual-write production in Phase 4D. If a future dual-write or write shadow is considered, it must be explicit, feature-flagged, separately approved, and reversible.

## Production Smoke Plan

Future production smoke must cover:

- read catalog
- read list
- read options
- read detail
- create with idempotency key in a safe test namespace or dry-run
- update a safe test template or dry-run
- invalid payload rejected
- dangerous fields rejected
- no external side effects
- fallback route still accessible
- rollback procedure verified

Smoke evidence must not use fixture/local_contract/demo data as production success.

## Rollback Plan

Required rollback design:

- immediate route owner rollback to `production_compat`
- feature flag disable if introduced later
- data rollback for create/update using before snapshots or compensating updates
- audit event review
- backup/snapshot requirement if DB writes are introduced
- rollback owner on call during any production smoke or switch

## Phase 4E Entry Conditions

Phase 4E cannot start until:

- this Phase 4D plan is merged
- legacy schema/service discovery is complete
- repository strategy is selected and owner-approved
- checker plan is accepted
- production config review is complete or explicitly deferred by owner
- rollback owner is assigned

Phase 4E is not automatically authorized by this PR.
