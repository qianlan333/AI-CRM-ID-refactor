# Phase 4AJ Action Templates Staging Smoke Package

## Status

Phase 4AJ prepares the action-templates staging smoke package.

- Staging smoke planning/package.
- No staging smoke execution by default.
- No production data.
- No production repository route owner enablement.
- No production route owner switch.
- No `production_compat` change.
- Legacy fallback retained.
- No external calls.
- No automation execution.
- `delete_ready`: false.

Current production behavior remains legacy `production_compat` fallback / `legacy_forward`. This PR does not change production ownership.

## How To Run

Dry-run/preflight example:

```bash
AICRM_ACTION_TEMPLATES_REPO_BACKEND=sqlalchemy \
AICRM_ACTION_TEMPLATES_STAGING_DATABASE_URL=<staging-safe-url> \
python3 tools/run_phase4aj_action_templates_staging_smoke.py \
  --output-json /tmp/phase4aj_action_templates_staging_smoke.json \
  --output-md /tmp/phase4aj_action_templates_staging_smoke.md
```

Owner-approved write smoke example:

```bash
AICRM_ACTION_TEMPLATES_REPO_BACKEND=sqlalchemy \
AICRM_ACTION_TEMPLATES_STAGING_DATABASE_URL=<staging-safe-url> \
AICRM_PHASE4AJ_STAGING_WRITE_APPROVED=1 \
python3 tools/run_phase4aj_action_templates_staging_smoke.py \
  --execute-writes \
  --output-json /tmp/phase4aj_action_templates_staging_write_smoke.json \
  --output-md /tmp/phase4aj_action_templates_staging_write_smoke.md
```

If `AICRM_ACTION_TEMPLATES_STAGING_DATABASE_URL` is missing, the runner does not connect to any DB. It writes blocked evidence with `result_status: not_executed_missing_staging_db` and `staging_smoke_executed: false`.

## Safety Guard

- The DB URL must contain at least one of: `staging`, `stage`, `test`, `local`, `dev`.
- The DB URL must not contain any of: `prod`, `production`, `primary`, `master`.
- If both allowed and forbidden markers are present, the runner refuses to run.
- The runner does not use generic DB env fallback.
- The runner does not use the Phase 4AH adapter DB env as a staging fallback.
- The runner does not use Phase 4AI test DB env as a staging fallback.
- No production DB is allowed.
- No external calls are allowed.
- Safe namespace is required for writes.

## Smoke Matrix

Read/preflight:

- schema availability.
- list action templates.

Write path, only when owner-approved:

- create CRM local template in safe namespace.
- idempotency replay.
- idempotency conflict.
- duplicate `template_code` rejection.
- missing name rejection.
- invalid status rejection.
- dangerous field rejection.
- audit event emitted.
- rollback payload present.
- side-effect safety all false.

## Safe Namespace

- `template_code` prefix: `phase4aj_staging_smoke_`.
- operator: `phase4aj_staging_smoke_operator`.
- idempotency key prefix: `phase4aj_staging_smoke_`.
- delete is not required in this phase.

## Evidence Boundaries

- Staging evidence only.
- Does not prove production behavior.
- Not production approval.
- Not canary.
- Not route-switch readiness.
- Not production write authorization.

## Owner Approval Checklist

- automation_engine owner: pending.
- integration_gateway owner: pending.
- staging DB/config owner: pending.
- rollback owner: pending.
- smoke operator: pending.

## Business Continuity

本 PR 只生成 action-templates staging smoke planning/package，不连接生产数据，不写生产，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。production path 仍由 legacy fallback 保持。

## Phase 4AK Recommendation

Recommended next step:

- `staging_smoke_execution_evidence_or_owner_approval_package`

Phase 4AK may execute staging smoke with owner approval or prepare owner approval evidence. It must not switch production owner, enable external calls, remove fallback, or authorize production write canary.
