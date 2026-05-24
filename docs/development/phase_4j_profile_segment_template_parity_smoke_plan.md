# Phase 4J Profile Segment Template Parity And Smoke Plan

## Status

Phase 4J is parity/smoke planning only.

- No runtime change.
- No production repository enablement.
- No production route owner switch.
- No `production_compat` change.
- No fallback removal.
- No smoke execution.
- No production data connection.
- No real external call.
- `delete_ready`: false.

Production traffic remains on the existing legacy `production_compat` fallback. The Phase 4I SQLAlchemy adapter remains opt-in only.

## Route Scope

Planning only for:

- `GET /api/admin/automation-conversion/profile-segment-templates/catalog`
- `GET /api/admin/automation-conversion/profile-segment-templates`
- `GET /api/admin/automation-conversion/profile-segment-templates/options`
- `GET /api/admin/automation-conversion/profile-segment-templates/{template_id}`
- `POST /api/admin/automation-conversion/profile-segment-templates`
- `PUT /api/admin/automation-conversion/profile-segment-templates/{template_id}`

No route is added, removed, or re-owned in this phase.

## Parity Matrix

| Area | Legacy source | Next adapter source | Comparison method | Acceptable differences | Blockers |
| --- | --- | --- | --- | --- | --- |
| catalog | `automation_conversion_templates.api_admin_automation_conversion_profile_segment_catalog`; `workflow_service.list_conversion_profile_segment_catalog` | `SqlAlchemyProfileSegmentTemplateRepository.profile_segment_template_catalog` | Compare keys, item count, identity fields, categories, warnings. | Next metadata such as `side_effect_safety`; draft/enabled owner-review warning. | Missing identity fields; fixture/local_contract/demo treated as production success. |
| list | `workflow_service.list_conversion_profile_segment_templates` | `SqlAlchemyProfileSegmentTemplateRepository.list_profile_segment_templates` | Compare filters, ordering, pagination, id/code/name/status, total. | Next aliases such as `template_id`; legacy UI labels may remain pending. | Unexplained count mismatch; status/enabled mismatch without approval. |
| options | `workflow_service.list_conversion_profile_segment_template_options` | `GetProfileSegmentTemplateOptionsQuery` with SQLAlchemy adapter | Compare option id/value/label/name/code/status. | Next route/source metadata. | Label/value mismatch; enabled-only mismatch. |
| detail | `workflow_service.get_conversion_profile_segment_template_bundle` | `SqlAlchemyProfileSegmentTemplateRepository.get_profile_segment_template` | Compare parent, categories, option mappings, missing behavior. | Next normalizes children into `rules.categories`. | Missing child rows; missing template does not map to not-found. |
| create validation | `workflow_service.create_conversion_profile_segment_template` | SQLAlchemy adapter + `profile_segments` validation | Compare required fields, invalid status, dangerous field rejection, error shape. | Next requires idempotency key. | Missing name or dangerous fields accepted. |
| create idempotency replay | Legacy has no dedicated idempotency store confirmed. | Companion idempotency response snapshot. | Same operator/key/hash returns same resource and replay marker. | Next safety is stronger than legacy. | Replay creates duplicate row. |
| create idempotency conflict | Legacy has no dedicated idempotency store confirmed. | Companion idempotency request hash. | Same operator/key with different payload returns conflict. | Next conflict is a safety improvement. | Conflict writes main data. |
| create duplicate template | Legacy table unique `template_code`; service duplicate behavior. | Adapter duplicate name/code guard. | Compare duplicate response and no partial child rows. | Next may reject duplicate name too. | Duplicate code creates second active template. |
| update validation | `workflow_service.update_conversion_profile_segment_template` | Adapter + `profile_segments` validation | Compare invalid status, dangerous fields, field preservation, error shape. | Optimistic locking warning is allowed until owner policy exists. | Dangerous fields accepted. |
| update missing template | Legacy update service | Adapter update method | Compare not-found behavior. | Envelope may differ while status/category is equivalent. | Missing template creates a row. |
| update before/after snapshot | Legacy current row/category/mapping state. | Companion audit snapshots. | Verify before and after include parent/child state. | Next audit is stronger. | Missing snapshot. |
| update child replacement | Legacy service replaces category/mapping children. | Adapter `_replace_categories`. | Compare final child set and transaction rollback. | Child row ids may differ. | Stale child mappings remain; partial commit on error. |
| audit log shape | Legacy operator snapshots or owner-approved log. | Companion audit table. | Compare operation/operator/resource/request/validation/safety. | Next audit may contain more fields. | `side_effect_safety` missing or true for real external effects. |
| rollback payload shape | Owner rollback playbook. | Adapter rollback payload. | Compare create compensating action and update restore snapshot. | Delete remains unapproved. | Missing created id or before/after payload. |

## Smoke Levels

| Level | Name | Authorized now | Owner approval | Production data | Writes | Scope |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | static/checker only | yes | no | no | no | Current Phase 4J. |
| 1 | local test DB | no | yes | no | yes | Uses `AICRM_NEXT_TEST_DATABASE_URL`; DB name must include `test`; safe namespace only. |
| 2 | staging | no | yes | no | yes | Staging DB/config only; feature flag only in staging; fallback retained. |
| 3 | production dry-run/read-only parity | no | yes | yes | no | Future only; production config review required. |
| 4 | production write canary | no | yes | yes | yes | Future only; separate PR required. |

## Feature Flag And Config Requirements

- Default backend remains `memory`.
- SQL backend is explicit: `AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND=sqlalchemy` or `PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND=sqlalchemy`.
- Database URL is explicit: `AICRM_PROFILE_SEGMENT_TEMPLATE_DATABASE_URL` or `AICRM_NEXT_TEST_DATABASE_URL`.
- Production auto-enable is false.
- Production route owner remains unchanged.
- Production fixture success is blocked.

## Smoke Data Namespace

- Template code prefix: `phase4j_smoke_`
- Operator: `phase4j_smoke_operator`
- Idempotency key prefix: `phase4j_smoke_`
- Cleanup/rollback: status/field revert in the safe namespace.
- Delete is not required and remains unapproved unless a later owner-approved PR adds it.

## Owner Approval Checklist

Before Phase 4K or any smoke execution:

- automation_engine owner: pending
- integration_gateway owner: pending
- business/ops owner: pending
- DB/config owner: pending
- rollback owner: pending
- smoke operator: pending

## Business Continuity

This plan does not affect the current automation operations production path. It does not execute smoke, connect production data, enable the production repository, switch route ownership, narrow `production_compat`, or remove fallback. Fixture/local_contract/demo data cannot be treated as production success.

## Phase 4K Recommendation

Recommended next step: local test DB parity harness implementation.

Phase 4K must not directly switch production route owner, enable production write canary, connect production data, remove fallback, or narrow `production_compat`.
