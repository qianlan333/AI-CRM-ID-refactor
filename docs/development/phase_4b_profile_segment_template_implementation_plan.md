# Phase 4B Profile Segment Template Implementation Plan

Status: Phase 4B planning only. This document does not change runtime,
implement a write route, add a business route, delete fallback, narrow
`production_compat`, enable real external calls, modify database schema,
authorize production cutover, or mark any route as `delete_ready`.

## Route Scope

In scope for planning:

- `GET /api/admin/automation-conversion/profile-segment-templates/catalog`
- `GET /api/admin/automation-conversion/profile-segment-templates`
- `GET /api/admin/automation-conversion/profile-segment-templates/options`
- `GET /api/admin/automation-conversion/profile-segment-templates/{template_id}`
- `POST /api/admin/automation-conversion/profile-segment-templates`
- `PUT /api/admin/automation-conversion/profile-segment-templates/{template_id}`

Out of scope:

- `DELETE` routes, unless legacy already has them and a later checker confirms
  the exact contract. Phase 4B does not invent delete behavior.
- run-due, execution, send, WeCom, OpenClaw, MCP, agent orchestration side
  effects, workflow execution, outbound task dispatch, and automation member
  state changes.

## Phase 4C Implementation Boundary

Phase 4C may implement only:

- read/list/detail/options/catalog parity
- create/update as bounded internal metadata writes

Phase 4C must not:

- trigger automation execution
- enqueue outbound tasks
- call WeCom/OpenClaw/MCP
- modify customer membership or pool state
- publish or activate workflows
- run timers
- delete legacy fallback
- mark `delete_ready`

## API Contract

The legacy route implementation currently exposes the six scoped routes from
`wecom_ability_service/http/automation_conversion.py` and delegates payloads to
`wecom_ability_service/http/automation_conversion_templates.py`. Phase 4C must
confirm the exact legacy contract before implementation. Where the legacy shape
is not fully proven by static code, the field is marked
`needs_legacy_contract_confirmation`.

### `GET /api/admin/automation-conversion/profile-segment-templates/catalog`

- action: questionnaire/profile segmentation catalog read.
- request params: none currently required by the Flask handler.
- success payload shape: `{ ok: true, items, total }`.
- validation errors: none currently visible; Phase 4C must preserve any legacy
  error behavior found during contract confirmation.
- idempotency behavior: not required for read.
- audit/operator identity requirement: not required for read.
- rollback behavior: not applicable for read; fallback remains retained.
- fallback behavior: legacy production facade / `production_compat` remains
  available until parity, checker, smoke, rollback, and owner approval are
  complete.
- production unavailable behavior: degraded/error, never fixture/local_contract
  success.

### `GET /api/admin/automation-conversion/profile-segment-templates`

- action: list profile segment template bundles.
- request params: `enabled_only` optional boolean, `program_id` optional.
- success payload shape: `{ ok: true, items, total }`, where each item is a
  template bundle.
- template fields observed in legacy code: `id`, `program_id`,
  `template_code`, `template_name`, `description`, `enabled`, `status`,
  `version`, `created_at`, `updated_at`, `questionnaire`,
  `segmentation_question`, `question_options`, `categories`, `validity`.
- compatibility aliases to evaluate in Phase 4C: `template_id` for `id`, `name`
  for `template_name`, `segment_key` or `code` for `template_code`,
  `conditions` or `rules` for category option mappings.
- fields needing legacy contract confirmation: `sort_order` at template level,
  because legacy code clearly exposes category `sort_order` but not template
  `sort_order`.
- validation errors: invalid query values must preserve legacy 400 behavior if
  found during contract confirmation.
- idempotency behavior: not required for read.
- audit/operator identity requirement: not required for read.
- rollback behavior: not applicable for read; fallback remains retained.
- fallback behavior: retained via `production_compat`.
- production unavailable behavior: degraded/error, never fixture/local_contract
  success.

### `GET /api/admin/automation-conversion/profile-segment-templates/options`

- action: list enabled profile segment templates as options.
- request params: `enabled_only` optional boolean, default true; `program_id`
  optional.
- success payload shape: `{ ok: true, items, total }`.
- validation errors: preserve legacy behavior for invalid query values if
  contract confirmation finds one.
- idempotency behavior: not required for read.
- audit/operator identity requirement: not required for read.
- rollback behavior: not applicable for read; fallback remains retained.
- fallback behavior: retained via `production_compat`.
- production unavailable behavior: degraded/error, never fixture/local_contract
  success.

### `GET /api/admin/automation-conversion/profile-segment-templates/{template_id}`

- action: get one profile segment template bundle.
- request params: path `template_id`; optional `program_id`.
- success payload shape: `{ ok: true, template_bundle, template,
  questionnaire, segmentation_question, question_options, categories, validity }`.
- not found: `{ ok: false, error }` with 404.
- validation errors: invalid `template_id` and program mismatch must not become
  fixture success.
- idempotency behavior: not required for read.
- audit/operator identity requirement: not required for read.
- rollback behavior: not applicable for read; fallback remains retained.
- fallback behavior: retained via `production_compat`.
- production unavailable behavior: degraded/error, never fixture/local_contract
  success.

### `POST /api/admin/automation-conversion/profile-segment-templates`

- action: create a bounded internal metadata template.
- request body: JSON object.
- supported legacy fields observed in code: `program_id`, `template_code`,
  `template_name`, `questionnaire_id`, `segmentation_question_id`,
  `description`, `enabled`, `categories`.
- compatibility aliases to evaluate in Phase 4C: `name` for `template_name`,
  `segment_key` or `code` for `template_code`, `conditions` or `rules` for
  `categories`. These aliases are not approved until legacy contract
  confirmation.
- success payload shape: `{ ok: true, template_bundle }`, HTTP 201.
- validation errors: missing `template_name`, duplicate `template_code`, missing
  `questionnaire_id`, missing `segmentation_question_id`, empty `categories`,
  no enabled category, enabled category without option bindings, invalid
  segmentation question, and dangerous side-effect fields must return a
  validation error.
- idempotency behavior: require an idempotency key or deterministic duplicate
  check before Phase 4C implementation. Retrying the same create must not create
  duplicate templates.
- duplicate behavior: duplicate `template_code` or normalized name/code must be
  deterministic and safe.
- audit/operator identity requirement: admin operator identity is required for
  `created_by`, `updated_by`, and an audit event.
- audit event shape: `{ action, route_family, template_id, operator_id,
  idempotency_key, before, after, created_at }`; no external event dispatch.
- rollback behavior: created template id must be captured. Rollback may disable
  or revert the template only if that behavior is approved; otherwise rollback
  must use a compensating update/status revert. Legacy fallback remains
  available.
- fallback behavior: retained through `production_compat` until Phase 4C parity,
  checker, smoke, rollback, and owner approval are complete.
- production unavailable behavior: degraded/error, never fixture/local_contract
  success.

### `PUT /api/admin/automation-conversion/profile-segment-templates/{template_id}`

- action: update a bounded internal metadata template.
- request params/body: path `template_id`; JSON patch or replacement payload.
  Phase 4C must explicitly choose patch semantics or replacement semantics.
- supported legacy fields observed in code: `program_id`, `template_code`,
  `template_name`, `questionnaire_id`, `segmentation_question_id`,
  `description`, `enabled`, `categories`.
- success payload shape: `{ ok: true, template_bundle }`.
- not found: `{ ok: false, error }` with 404.
- validation errors: missing/stale template, program mismatch, duplicate
  `template_code`, invalid questionnaire/question/category payload, dangerous
  side-effect fields, and stale update must return validation or 404.
- idempotency behavior: target explicit `template_id`; require stale update
  protection through version/updated_at/etag or another deterministic guard.
- field preservation: Phase 4C must preserve fields omitted from a patch, or
  explicitly document replacement semantics before implementation.
- audit/operator identity requirement: admin operator identity is required for
  `updated_by` and an audit event.
- audit event shape: `{ action, route_family, template_id, operator_id,
  idempotency_key, before, after, updated_at }`; no external event dispatch.
- rollback behavior: capture before/after snapshot or audit snapshot so an
  update can be reverted through a compensating update. Legacy fallback remains
  available.
- fallback behavior: retained through `production_compat` until Phase 4C parity,
  checker, smoke, rollback, and owner approval are complete.
- production unavailable behavior: degraded/error, never fixture/local_contract
  success.

## Validation Guardrails

Phase 4C must validate:

- required fields: `template_name`, `questionnaire_id`,
  `segmentation_question_id`, `categories` for create; explicit `template_id`
  for update.
- max lengths for text fields such as `template_name`, `template_code`, and
  `description`.
- allowed status values, mapped to legacy `enabled` / `status`.
- JSON/rules schema for `categories`, option mappings, and any compatibility
  `conditions` / `rules` aliases.
- external-call config fields are disallowed.
- payloads attempting execution, send, timer, workflow activation, task
  dispatch, WeCom, OpenClaw, MCP, or customer pool state changes are rejected.
- unknown dangerous fields are rejected instead of silently persisted.

## Rollback

Per-write rollback must be possible before Phase 4C implementation:

- Created template id must be emitted or auditable. If delete is not approved,
  rollback uses status/field reversion instead of deletion.
- Updated template must capture before/after snapshot or equivalent audit
  snapshot.
- Legacy fallback must remain available.
- `production_compat` remains unchanged in Phase 4C unless separately approved.

## Required Phase 4C Checker

The Phase 4C checker must verify:

- exact Next route owner only for explicitly opted-in routes
- legacy fallback retained
- no external side effects
- no run-due/execution/send paths touched
- production unavailable is degraded/error
- fixture/local_contract is not accepted in production success path
- idempotency required for create
- audit/operator identity captured
- validation rejects dangerous fields
- rollback information emitted or auditable

## Required Phase 4C Smoke Tests

Phase 4C must include smoke coverage for:

- list templates
- create draft/internal template with idempotency key
- retry create with the same idempotency key
- update template
- invalid payload rejected
- unknown template update returns 404 or validation error
- production unavailable does not return fixture success
- fallback path still present

## Owner Signoff Checklist

- automation_engine owner: pending
- integration_gateway owner: pending
- business owner / operations owner: pending
- rollback owner: pending
- production smoke owner: pending
