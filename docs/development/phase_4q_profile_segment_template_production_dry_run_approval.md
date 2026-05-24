# Phase 4Q Profile Segment Template Production Dry-Run Approval

## Status

Phase 4Q creates the production dry-run owner approval package only.

- Production dry-run approval package only.
- Production dry-run is not run by this PR.
- No production data connection.
- No production repository enablement.
- No production route owner switch.
- No `production_compat` change.
- Legacy fallback retained.
- No external calls.
- No production write canary.
- `delete_ready`: false.

This package prepares approvals, environment confirmation, execution window, read-only / validation-shadow scope, stop conditions, evidence requirements, rollback / abort plan, and Phase 4R entry criteria. It does not run any production dry-run level and does not connect to production data.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Production dry-run approval / fallback boundary:

- `aicrm_next.integration_gateway`

Approval package covers only:

- `GET /api/admin/automation-conversion/profile-segment-templates/catalog`
- `GET /api/admin/automation-conversion/profile-segment-templates`
- `GET /api/admin/automation-conversion/profile-segment-templates/options`
- `GET /api/admin/automation-conversion/profile-segment-templates/{template_id}`
- `POST /api/admin/automation-conversion/profile-segment-templates`
- `PUT /api/admin/automation-conversion/profile-segment-templates/{template_id}`

No business route is added, removed, or modified. Production facade enabled mode remains owned by the legacy `production_compat` fallback. The SQLAlchemy adapter exists but is not the production owner.

## Approval Checklist

All approvals remain pending until a later Phase 4R request records explicit signoff.

| Approval | Status | Required before Phase 4R |
| --- | --- | --- |
| automation_engine owner | pending | Yes |
| integration_gateway owner | pending | Yes |
| DB/config owner | pending | Yes |
| business/ops owner | pending | Yes |
| rollback owner | pending | Yes |
| dry-run operator | pending | Yes |
| release/config reviewer | pending | Yes |
| security/data reviewer | pending | Yes |

## Approved Dry-Run Levels

Phase 4Q does not authorize execution. It only defines what a later Phase 4R request may ask for.

Allowed to request in Phase 4R:

- Level 1: production read-only parity dry-run.
- Level 2: production validation shadow for create/update, no writes.

Not allowed:

- Level 3: production safe-namespace write dry-run.
- Level 4: production write canary.

## Required Environment Confirmation

The later execution package must confirm these items without exposing secrets:

- Production DB/config source.
- Secret redaction.
- No raw DB URL in report.
- No raw PII in evidence.
- Route owner remains legacy `production_compat` fallback.
- Fallback validation command.
- `production_compat` unchanged.
- SQLAlchemy adapter flag must not become default.
- Any production dry-run flag must be temporary and explicitly scoped.
- Fixture/local_contract/demo evidence must not be mixed with production dry-run evidence.

## Execution Window Plan

The later Phase 4R request must fill these before any command is run:

- Who executes: pending dry-run operator.
- When to execute: pending approved production config review window.
- Expected duration: pending, bounded by read-only and validation-shadow cases.
- Communication channel: pending owner-designated channel.
- Evidence location: pending durable location for redacted JSON/Markdown reports.
- Stop condition: stop on missing approval, incomplete config review, route owner drift, fallback validation failure, external call detection, write attempt, or redaction failure.
- Rollback owner: pending.
- Fallback validation owner: pending.

## Production Dry-Run Command Templates

Level 1 read-only parity command template, not executable by this PR:

```bash
AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND=sqlalchemy \
AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DRY_RUN_APPROVED=1 \
python3 tools/run_phase4r_profile_segment_template_production_dry_run.py \
  --read-only \
  --output-json /tmp/phase4r_profile_segment_production_readonly_dry_run.json \
  --output-md /tmp/phase4r_profile_segment_production_readonly_dry_run.md
```

The Phase 4R runner does not exist yet and must be implemented in a later PR.

## Stop Conditions

Stop immediately if any of these conditions occur:

- Owner approval missing.
- Production config review incomplete.
- Route owner changed.
- `production_compat` changed.
- Fallback validation failed.
- External call detected.
- Write attempted in read-only dry-run.
- Secret redaction failed.
- PII redaction failed.
- `side_effect_safety` is not false.
- Unexpected production data mutation.

## Rollback / Abort Plan

- Disable the dry-run flag.
- Verify `production_compat` fallback is still active.
- Verify no route owner switch occurred.
- Preserve evidence.
- Notify owners.
- No data rollback should be needed for Level 1/2 because writes are forbidden.
- If any write is detected, trigger incident-style review.

## Evidence Package

Future execution evidence must include:

- Runner JSON report.
- Runner Markdown report.
- Approval snapshot.
- Config summary without secrets.
- Route owner unchanged evidence.
- `production_compat` retained evidence.
- Fallback validation.
- Read parity summary.
- Validation shadow summary if applicable.
- Skipped/write-blocked summary.
- Side-effect safety summary.
- Redaction summary.
- Operator/timestamp.
- Owner signoff.

## Business Continuity

This PR only generates the Phase 4Q production dry-run owner approval package. It does not run production dry-run, does not connect production data, does not enable production repository, does not switch production route owner, does not remove legacy fallback, and does not modify `production_compat`. Current automation operations configuration pages and APIs remain unaffected.

Any future production dry-run execution, production repository enablement, route ownership switch, or write canary must be handled in a separate PR after owner approval, checker, smoke, rollback, and production config review requirements are satisfied.

## Phase 4R Recommendation

Recommended next step: implement production read-only dry-run runner.

Phase 4R may implement a production read-only dry-run runner, but it must not execute production dry-run by default, must not switch route owner, must not remove fallback, and must not enable a production write canary.
