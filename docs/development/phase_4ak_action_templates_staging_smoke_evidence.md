# Phase 4AK Action Templates Staging Smoke Evidence Gate

## Status

Phase 4AK adds an action-templates staging smoke execution evidence gate. It does not use production data, does not enable the production repository as route owner, does not switch production route ownership, does not change `production_compat`, retains the legacy fallback, performs no external calls, performs no automation execution, and keeps `delete_ready` false.

This phase only prepares and gates owner-approved staging evidence for `/api/admin/automation-conversion/action-templates*`. Production remains legacy `production_compat` fallback / `legacy_forward`.

## Approval Requirements

Staging smoke evidence can call the Phase 4AJ runner only when all required gates pass:

- `AICRM_ACTION_TEMPLATES_REPO_BACKEND=sqlalchemy`
- `AICRM_ACTION_TEMPLATES_STAGING_DATABASE_URL` is present and passes the staging URL safety guard
- `AICRM_PHASE4AK_STAGING_SMOKE_APPROVED=1`

Write smoke additionally requires:

- `--execute-writes`
- `AICRM_PHASE4AK_STAGING_WRITE_APPROVED=1`

If any required DB/config/approval gate is missing, the tool returns blocked evidence and does not call the Phase 4AJ runner.

## How To Run Blocked Or Read-Only Evidence

```bash
AICRM_ACTION_TEMPLATES_REPO_BACKEND=sqlalchemy \
AICRM_ACTION_TEMPLATES_STAGING_DATABASE_URL=<staging-safe-url> \
AICRM_PHASE4AK_STAGING_SMOKE_APPROVED=1 \
python3 tools/run_phase4ak_action_templates_staging_smoke_evidence.py \
  --output-json /tmp/phase4ak_action_templates_staging_smoke.json \
  --output-md /tmp/phase4ak_action_templates_staging_smoke.md
```

## How To Run Owner-Approved Write Smoke

```bash
AICRM_ACTION_TEMPLATES_REPO_BACKEND=sqlalchemy \
AICRM_ACTION_TEMPLATES_STAGING_DATABASE_URL=<staging-safe-url> \
AICRM_PHASE4AK_STAGING_SMOKE_APPROVED=1 \
AICRM_PHASE4AK_STAGING_WRITE_APPROVED=1 \
python3 tools/run_phase4ak_action_templates_staging_smoke_evidence.py \
  --execute-writes \
  --output-json /tmp/phase4ak_action_templates_staging_write_smoke.json \
  --output-md /tmp/phase4ak_action_templates_staging_write_smoke.md
```

## Safety Guard

The staging DB URL must contain at least one allowed marker: `staging`, `stage`, `test`, `local`, or `dev`. It must not contain any forbidden marker: `prod`, `production`, `primary`, or `master`. If both allowed and forbidden markers appear, execution is blocked.

The evidence gate does not fall back to `DATABASE_URL`, `AICRM_ACTION_TEMPLATES_DATABASE_URL`, `AICRM_ACTION_TEMPLATES_TEST_DATABASE_URL`, production DB env, or shared settings database URL. It does not call external systems. Writes, if owner-approved in a later run, are limited to the safe namespace:

- `template_code` prefix: `phase4aj_staging_smoke_`
- operator: `phase4aj_staging_smoke_operator`
- idempotency key prefix: `phase4aj_staging_smoke_`

## Evidence Boundaries

Staging evidence is staging evidence only. It is not parity for production, not approval for production, not canary approval, and not route-switch readiness. It cannot authorize production repository route enablement, production write, production owner switch, fallback removal, or production write canary.

## Owner Approval Checklist

- automation_engine owner: pending
- integration_gateway owner: pending
- staging DB/config owner: pending
- rollback owner: pending
- smoke operator: pending

## Phase 4AL Recommendation

If Phase 4AK evidence remains blocked, Phase 4AL should continue staging approval/config closure. If staging smoke evidence passes, Phase 4AL may plan production dry-run evidence. Phase 4AL still must not switch the production owner, remove fallback, enable external calls, or treat staging evidence as production approval.
