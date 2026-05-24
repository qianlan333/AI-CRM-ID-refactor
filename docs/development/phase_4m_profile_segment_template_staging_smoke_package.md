# Phase 4M Profile Segment Template Staging Smoke Package

## Status

Phase 4M adds a staging smoke harness / execution package only.

- Smoke is not executed by this PR.
- No production data connection.
- No production repository enablement.
- No production route owner switch.
- No `production_compat` change.
- Legacy fallback retained.
- No external calls.
- `delete_ready`: false.

The runner is a manually invoked package for the profile-segment-template route family. It is not wired into CI default execution and does not change production route behavior.

## Manual Dry-Run

Default mode is dry-run. It validates safety guards and payload contracts without staging DB writes:

```bash
AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND=sqlalchemy \
AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL=postgresql://user:pass@host/staging_ai_crm \
python3 tools/run_phase4m_profile_segment_template_staging_smoke.py \
  --dry-run \
  --output-json /tmp/phase4m_staging_smoke.json \
  --output-md /tmp/phase4m_staging_smoke.md
```

Owner-approved write execution must be explicit:

```bash
AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND=sqlalchemy \
AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL=postgresql://user:pass@host/staging_ai_crm \
AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_OPERATOR=phase4m_staging_smoke_operator \
AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_NAMESPACE=phase4m_staging_smoke \
python3 tools/run_phase4m_profile_segment_template_staging_smoke.py \
  --execute-writes \
  --output-json /tmp/phase4m_staging_smoke_execute.json \
  --output-md /tmp/phase4m_staging_smoke_execute.md
```

The write example is owner-approved only and remains outside this PR execution.

## Safety Guard

- `AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL` is required.
- `AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND=sqlalchemy` is required.
- The runner never falls back to `DATABASE_URL` or shared production settings.
- The DB URL must contain one of `staging`, `stage`, `test`, `local`, or `dev`.
- The DB URL must not contain `prod`, `production`, `primary`, or `master`.
- If allowed and forbidden markers both appear, the runner fails.
- Dry-run is the default.
- Writes require `--execute-writes`.
- Writes must use the safe namespace and staging DB URL only.

## Smoke Matrix

Dry-run/report checks:

- validate create payload
- validate idempotency plan
- validate update payload
- validate dangerous field rejection

Read checks in owner-approved execute mode:

- catalog
- list
- options
- detail after a safe namespace template is created

Write checks in owner-approved execute mode:

- create with idempotency key
- replay with same key
- conflict with same key and different payload
- duplicate template rejected
- update safe namespace template
- update missing template
- invalid payload rejected
- dangerous field rejected
- audit row exists
- rollback payload exists
- side-effect safety remains false

## Safe Namespace

- Template code prefix: `phase4m_staging_smoke_`
- Operator: `phase4m_staging_smoke_operator`
- Idempotency key prefix: `phase4m_staging_smoke_`
- Deletion is not required and remains unapproved.
- Rollback uses the returned rollback payload and compensating status/field revert.

## Failure Handling

- Stop on first failed write check.
- Disable the staging feature flags before retry.
- Use rollback payload or compensating status/field revert for safe namespace rows.
- Review companion audit rows.
- Validate fallback remains available and unchanged.
- Notify automation_engine, integration_gateway, DB/config, business/ops, rollback, and smoke owners.

## Business Continuity

Current production route ownership remains legacy fallback. The staging runner is not connected to production route owner, does not use production data, and does not narrow `production_compat`. No production rollback is needed for this PR because no production behavior changes.

## Phase 4N Recommendation

Phase 4N may execute staging smoke or first package owner approval. Production dry-run remains unauthorized, production route switch remains unauthorized, and production write canary remains unauthorized.
