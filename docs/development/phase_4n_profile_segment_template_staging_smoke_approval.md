# Phase 4N Profile Segment Template Staging Smoke Approval

## Status

Phase 4N creates the staging smoke owner approval package only.

- Staging smoke approval package only.
- Smoke is not run by this PR.
- No DB connection.
- No production data.
- No production repository enablement.
- No production route owner switch.
- No `production_compat` change.
- Legacy fallback retained.
- No external calls.
- `delete_ready`: false.

This package prepares the manual approval, environment confirmation, execution window, rollback plan, stop conditions, and evidence checklist for a later staging smoke execution. It does not execute the Phase 4M runner and does not authorize staging smoke by itself.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Staging smoke approval / fallback boundary:

- `aicrm_next.integration_gateway`

Covered route family:

- `GET /api/admin/automation-conversion/profile-segment-templates/catalog`
- `GET /api/admin/automation-conversion/profile-segment-templates`
- `GET /api/admin/automation-conversion/profile-segment-templates/options`
- `GET /api/admin/automation-conversion/profile-segment-templates/{template_id}`
- `POST /api/admin/automation-conversion/profile-segment-templates`
- `PUT /api/admin/automation-conversion/profile-segment-templates/{template_id}`

This PR does not add, remove, or modify business routes. Local/staging runner code already exists from Phase 4M, but it is not invoked here. Production facade enabled mode remains owned by the legacy `production_compat` fallback.

## Approval Checklist

All approvals remain pending until a later Phase 4O execution request records explicit owner signoff.

| Approval | Status | Required before execution |
| --- | --- | --- |
| automation_engine owner | pending | Yes |
| integration_gateway owner | pending | Yes |
| DB/config owner | pending | Yes |
| business/ops owner | pending | Yes |
| rollback owner | pending | Yes |
| smoke operator | pending | Yes |
| release/config reviewer | pending | Yes |

## Environment Confirmation

The execution request must confirm the staging DB URL source without exposing secrets.

- Staging DB URL source: pending owner-provided secure configuration reference.
- The DB URL must include one of: `staging`, `stage`, `test`, `local`, or `dev`.
- The DB URL must not include: `prod`, `production`, `primary`, or `master`.
- Required feature flag: `AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND=sqlalchemy`.
- Required staging DB variable: `AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL`.
- `DATABASE_URL` fallback is not allowed.
- Production data is not allowed.
- Fixture, local contract, or demo evidence cannot be treated as production parity success.
- Staging smoke evidence cannot be treated as production approval.

## Execution Window Plan

The later execution package must fill these fields before any smoke command is run:

- Who executes: pending smoke operator.
- When to execute: pending approved staging maintenance/test window.
- Expected duration: pending, expected to be short and bounded by the Phase 4M smoke matrix.
- Communication channel: pending owner-designated channel.
- Evidence location: pending durable location for JSON/Markdown reports and signoff.
- Primary stop condition: stop immediately if DB URL safety fails, any write check fails, any external side effect is detected, or fallback validation fails.

## Smoke Command Template

Dry-run command for a later owner-approved execution window:

```bash
AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND=sqlalchemy \
AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL=<staging-safe-url> \
python3 tools/run_phase4m_profile_segment_template_staging_smoke.py \
  --dry-run \
  --output-json /tmp/phase4n_staging_smoke_dry_run.json \
  --output-md /tmp/phase4n_staging_smoke_dry_run.md
```

Write smoke command, owner-approved only:

```bash
AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND=sqlalchemy \
AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL=<staging-safe-url> \
python3 tools/run_phase4m_profile_segment_template_staging_smoke.py \
  --execute-writes \
  --output-json /tmp/phase4n_staging_smoke_write.json \
  --output-md /tmp/phase4n_staging_smoke_write.md
```

The write command must not be run until all approvals are recorded and the dry-run result is accepted.

## Stop Conditions

Stop the smoke immediately if any of the following happens:

- DB URL safety fails.
- Any smoke write fails.
- Idempotency conflict is unexpected.
- Audit row is missing.
- Rollback payload is missing.
- `side_effect_safety` is not false.
- External call is detected.
- Production marker is detected.
- Fallback validation fails.

## Rollback And Cleanup Plan

Rollback and cleanup must be prepared before execution:

- Disable staging feature flags.
- Use safe namespace rollback or compensating update.
- Review audit rows.
- Preserve evidence.
- Do not delete records unless separately approved.
- Validate fallback remains available and unchanged.

## Evidence Package

The later execution must preserve:

- Runner JSON report.
- Runner Markdown report.
- DB URL safety summary without secrets.
- Smoke matrix summary.
- Failed/skipped details.
- Audit/rollback evidence.
- `side_effect_safety` summary.
- Operator and timestamp.
- Owner signoff.

## Business Continuity

This PR only generates the Phase 4N staging smoke owner approval package. It does not run staging smoke, does not connect to staging DB or production data, does not enable production repository, does not switch production route owner, does not remove legacy fallback, and does not modify `production_compat`. Current automation operations configuration pages and APIs remain unaffected.

Any later staging smoke execution, production dry-run, or production write canary must be handled in a separate PR after owner approval, checker, smoke, rollback, and production config review requirements are satisfied.

## Phase 4O Recommendation

Recommended next step: execute staging smoke only after owner approval.

Phase 4O may run staging smoke dry-run first, then owner-approved write smoke. Production dry-run remains unauthorized, route switch remains unauthorized, and production write canary remains unauthorized.
