# Phase 4Y Profile Segment Template Production Read-Only Preflight

## Status

Phase 4Y adds a production read-only dry-run preflight collector and evidence model. It reads closure status, explicit environment flags, and CLI flags, then reports whether a later Phase 4Z production read-only dry-run may be attempted.

- Production read-only dry-run preflight only.
- No production dry-run execution.
- No production DB connection.
- No production write.
- No production repository route enablement.
- No route ownership switch.
- No `production_compat` change.
- Legacy fallback retained.
- No external calls.
- `delete_ready`: false.

No business route is added, removed, or modified. Production facade enabled mode remains owned by the legacy `production_compat` fallback. The SQLAlchemy adapter exists but is not the production route owner.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Production dry-run approval / config preflight / fallback boundary:

- `aicrm_next.integration_gateway`

Preflight gate only for read-only routes:

- `GET /api/admin/automation-conversion/profile-segment-templates/catalog`
- `GET /api/admin/automation-conversion/profile-segment-templates`
- `GET /api/admin/automation-conversion/profile-segment-templates/options`
- `GET /api/admin/automation-conversion/profile-segment-templates/{template_id}`

## Closure Status Model

Each closure item can be one of:

- `pending`
- `completed`
- `blocked`
- `not_applicable`

Closure items:

| Item | Default status |
| --- | --- |
| `automation_engine_owner_approval` | pending |
| `integration_gateway_owner_approval` | pending |
| `db_config_owner_approval` | pending |
| `business_owner_approval` | pending |
| `rollback_owner_assigned` | pending |
| `dry_run_operator_assigned` | pending |
| `release_config_reviewer_approval` | pending |
| `security_data_reviewer_approval` | pending |
| `production_config_review_completed` | pending |
| `production_db_env_confirmed` | pending |
| `read_only_flags_confirmed` | pending |
| `evidence_path_confirmed` | pending |
| `fallback_validation_plan_confirmed` | pending |
| `secret_redaction_confirmed` | pending |
| `pii_redaction_confirmed` | pending |

Fixture, local_contract, demo, local test DB, and staging-only evidence cannot be treated as production dry-run success.

## Preflight Collector Behavior

The collector reads:

- Phase 4Y YAML defaults.
- Phase 4X YAML as the upstream final gate source.
- Optional closure status file via `--closure-status-file`.
- Environment flags.
- CLI arguments.

The optional closure status file can be YAML or JSON and should use the same field names as `closure_items`. The collector validates status values, merges the optional status file over the Phase 4Y defaults, and then uses environment and CLI presence checks only as preflight evidence.

The collector does not connect to any DB, does not call the dry-run runner, and does not perform a production dry-run.

Environment checks:

- `AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED=1`
- `AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED=1`
- `AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND=sqlalchemy`
- `AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL` present

CLI checks:

- `--read-only`
- `--confirm-no-writes`

Reports must redact secrets, must not export raw PII, and must not export raw payloads.

## Readiness Decision

Current default decision:

- `ready_for_phase_4z_readonly_dry_run_execution: false`

Missing items:

- Closure form items remain pending unless a later owner-supplied status file marks them completed.
- Owner approval env is not assumed.
- Production config review env is not assumed.
- Production DB env is not assumed.
- Read-only/no-write flags are not assumed.
- Evidence path and fallback validation plan are not assumed.

Next owner actions:

- Complete automation_engine owner approval.
- Complete integration_gateway owner approval.
- Complete DB/config owner approval.
- Complete business/ops owner approval.
- Assign rollback owner and dry-run operator.
- Complete release/config and security/data review.

Next config actions:

- Confirm `AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED=1`.
- Confirm `AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED=1`.
- Confirm `AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND=sqlalchemy`.
- Confirm `AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL` only in the scoped manual environment.
- Confirm `--read-only` and `--confirm-no-writes`.

Next evidence actions:

- Confirm redacted JSON and Markdown evidence paths.
- Confirm fallback validation plan.
- Confirm secret redaction.
- Confirm PII redaction.
- Keep raw payload export forbidden.

## Phase 4Z Runbook Preview

This command template is for a future PR only and is not executable by Phase 4Y:

```bash
AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED=1 \
AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED=1 \
AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND=sqlalchemy \
AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL=<redacted> \
python3 tools/run_phase4u_profile_segment_template_production_readonly_dry_run_evidence_and_review.py \
  --read-only \
  --confirm-no-writes \
  --output-json /tmp/phase4z_profile_segment_readonly_dry_run.json \
  --output-md /tmp/phase4z_profile_segment_readonly_dry_run.md
```

Phase 4Z remains constrained to:

- Read-only only.
- No create/update/delete.
- No production write.
- No route owner switch.
- No fallback removal.
- No `production_compat` change.
- No external calls.
- No raw PII export.
- No secret export.

## Business Continuity

本 PR 只生成 Phase 4Y production read-only dry-run preflight collector，不连接生产数据，不执行 dry-run，不写生产，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。当前 production path 仍由 legacy fallback 保持。

## Risk / Rollback

Rollback is deleting the Phase 4Y document, YAML, preflight collector, checker, and test. Runtime behavior, production data, route ownership, fallback behavior, `production_compat`, schema, and migrations are unchanged.

## Phase 4Z Recommendation

If Phase 4Y reports `ready=false`, Phase 4Z should continue closure status. If Phase 4Y reports `ready=true`, Phase 4Z may execute production read-only dry-run only after explicit owner confirmation; it must not write production data or switch route owner.
