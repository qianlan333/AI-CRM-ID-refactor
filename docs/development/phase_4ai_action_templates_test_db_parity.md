# Phase 4AI Action Templates Test DB Parity Harness

## Status

Phase 4AI adds a local/test DB adapter parity harness for action-templates.

- Local test DB adapter parity harness.
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

Example:

```bash
AICRM_ACTION_TEMPLATES_REPO_BACKEND=sqlalchemy \
AICRM_ACTION_TEMPLATES_TEST_DATABASE_URL=<local-test-db-url> \
python3 tools/run_phase4ai_action_templates_test_db_parity.py \
  --output-json /tmp/phase4ai_action_templates_test_db_parity.json \
  --output-md /tmp/phase4ai_action_templates_test_db_parity.md
```

If `AICRM_ACTION_TEMPLATES_TEST_DATABASE_URL` is missing, the harness does not connect to any DB. It writes blocked evidence with `result_status: not_executed_missing_test_db` and `adapter_smoke_executed: false`.

## Safety Guard

- The DB URL must contain at least one of: `test`, `local`, `dev`, `tmp`.
- The DB URL must not contain any of: `prod`, `production`, `primary`, `master`.
- If both allowed and forbidden markers are present, the harness refuses to run.
- The harness does not use generic DB env fallback.
- The harness does not use the Phase 4AH adapter DB env as a test harness fallback.
- The harness does not use profile-segment DB env.
- No production DB is allowed.
- No external calls are allowed.

## Harness Matrix

Schema:

- `automation_operation_templates` availability.
- `automation_operation_template_idempotency` availability.
- `automation_operation_template_audit_log` availability.

Read:

- `list_action_templates`.

Create:

- create CRM local template with idempotency key.
- idempotency replay.
- idempotency conflict.
- duplicate `template_code` rejection.
- missing name rejection.
- invalid status rejection.
- dangerous field rejection.
- audit event emitted.
- rollback payload present.
- side-effect safety all false.

## Evidence Boundaries

- Local/test DB evidence only.
- Does not prove production behavior.
- Not production approval.
- Not canary.
- Not route-switch readiness.
- Not production write authorization.

## Business Continuity

本 PR 只实现 action-templates local test DB adapter parity harness，不连接生产数据，不写生产，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。production path 仍由 legacy fallback 保持。

## Phase 4AJ Recommendation

Recommended next step:

- `staging_smoke_planning_or_package`

Phase 4AJ may prepare action-templates staging smoke planning/package. It must not switch production owner, enable external calls, remove fallback, or authorize production write canary.
