# Phase 4L Profile Segment Template Staging Smoke Plan

## Status

Phase 4L is staging smoke planning only.

- No smoke execution in this PR.
- No production data connection.
- No production repository enablement.
- No production route owner switch.
- No `production_compat` change.
- Legacy fallback retained.
- No external calls.
- `delete_ready`: false.

The plan covers the profile-segment-template route family only. It does not add, remove, or modify any business route.

## Route Scope

Planning only for:

- `GET /api/admin/automation-conversion/profile-segment-templates/catalog`
- `GET /api/admin/automation-conversion/profile-segment-templates`
- `GET /api/admin/automation-conversion/profile-segment-templates/options`
- `GET /api/admin/automation-conversion/profile-segment-templates/{template_id}`
- `POST /api/admin/automation-conversion/profile-segment-templates`
- `PUT /api/admin/automation-conversion/profile-segment-templates/{template_id}`

Current owner remains unchanged: local/non-production has the Next native contract and opt-in SQLAlchemy adapter, while production facade enabled mode remains on legacy `production_compat` fallback.

## Staging Smoke Prerequisites

- A staging DB URL and config owner must be recorded before any run package is approved.
- The DB must be non-production.
- The DB URL or database name must include one of `staging`, `stage`, `test`, `local`, or `dev`.
- Companion tables must exist:
  - `automation_profile_segment_template_idempotency`
  - `automation_profile_segment_template_audit_log`
- Main profile segment tables must exist:
  - `automation_profile_segment_template`
  - `automation_profile_segment_category`
  - `automation_profile_segment_option_mapping`
- Safe namespace must be empty or cleanup-approved.
- Feature flags must be explicitly set only for the staging run context:
  - `AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND=sqlalchemy`
  - `AICRM_PROFILE_SEGMENT_TEMPLATE_DATABASE_URL=<staging db>`
- Production route owner must remain unchanged.
- `production_compat` fallback must remain retained.

Fixture/local_contract/demo responses cannot be accepted as production success evidence.

## Staging Smoke Matrix

Read checks:

- catalog read
- list read
- options read
- detail read

Write checks:

- create in safe namespace with idempotency key
- create replay with same key
- create conflict with same key and different payload
- duplicate `template_code` / name rejection
- update safe namespace template
- update missing template
- invalid payload rejection
- dangerous field rejection
- audit log row created
- rollback payload present
- `side_effect_safety` all false
- fallback route still available and unchanged

## Safe Namespace

- Template code prefix: `phase4l_staging_smoke_`
- Operator: `phase4l_staging_smoke_operator`
- Idempotency key prefix: `phase4l_staging_smoke_`
- Cleanup strategy: compensating status/field revert inside the safe namespace.
- Rollback strategy: use returned rollback payload plus audit before/after snapshots.
- Delete is not required and remains unapproved unless a later owner-approved PR explicitly allows it.

## Execution Rules

- Manual approval is required before any staging smoke run.
- It must not run in CI by default.
- It must not use production DB.
- It must not call external systems.
- It must not execute automation workflows.
- It must not send messages.
- It must not alter customer pool state.
- It must keep production route ownership and `production_compat` behavior unchanged.

## Failure Handling

- Stop on first write failure.
- Disable the staging feature flag before any retry.
- Roll back data using the returned rollback payload or compensating status/field revert.
- Review companion audit rows before declaring the smoke package clean.
- Notify automation_engine, integration_gateway, DB/config, rollback, and business/ops owners.
- Validate fallback remains available and unchanged after the failure.

## Owner Approval Checklist

Before Phase 4M or any smoke run package:

- automation_engine owner: pending
- integration_gateway owner: pending
- DB/config owner: pending
- business/ops owner: pending
- rollback owner: pending
- smoke operator: pending

## Business Continuity

This plan does not affect the current automation operations production path. It does not run smoke, connect production data, enable production repository traffic, switch route ownership, narrow `production_compat`, remove fallback, or trigger external side effects.

## Phase 4M Recommendation

Recommended next step: staging smoke harness/tool implementation or staging smoke execution package.

Phase 4M must still avoid production dry-run, production route ownership switch, production write canary, fallback removal, and production data connection unless a later owner-approved PR explicitly changes the scope.
