# Phase 4S Profile Segment Template Production Read-Only Dry-Run Evidence

## Status

Phase 4S generates a production read-only dry-run evidence package and evidence gate.

- Production read-only dry-run evidence package.
- No production writes.
- No production route owner switch.
- No production repository route enablement.
- No `production_compat` change.
- Legacy fallback retained.
- No external calls.
- `delete_ready`: false.

This PR does not add, remove, or modify any business route. Production facade enabled mode remains owned by the legacy `production_compat` fallback. The SQLAlchemy adapter exists, but it is not the production route owner.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Production dry-run / fallback boundary:

- `aicrm_next.integration_gateway`

Read-only evidence only for:

- `GET /api/admin/automation-conversion/profile-segment-templates/catalog`
- `GET /api/admin/automation-conversion/profile-segment-templates`
- `GET /api/admin/automation-conversion/profile-segment-templates/options`
- `GET /api/admin/automation-conversion/profile-segment-templates/{template_id}`

## Execution Result

Current evidence status:

- `not_executed_missing_approval`

The Phase 4S evidence gate records blocked evidence because the PR does not include owner approval, production config review confirmation, a production DB URL, or execution flags. If any required condition is missing, the tool must not call the Phase 4R runner, must not connect to the DB, and must not claim dry-run success.

Allowed result statuses:

- `not_executed_missing_approval`
- `not_executed_config_not_reviewed`
- `not_executed_missing_production_db`
- `not_executed_read_only_flags_missing`
- `not_executed_safety_failed`
- `read_only_dry_run_executed`

## Required Evidence Fields

Every Phase 4S JSON/Markdown evidence report must include:

- Command attempted or not-attempted reason.
- Approval flags summary.
- Production config reviewed summary.
- DB URL redaction summary.
- Route owner unchanged evidence.
- `production_compat` retained evidence.
- Read parity summary if executed.
- Skipped details.
- Side-effect safety summary.
- `writes_attempted: false`.
- Operator.
- Timestamp.

Reports must redact DB credentials, must not export raw payloads, and must not export raw PII.

## Evidence Gate

Tool:

```bash
python3 tools/run_phase4s_profile_segment_template_production_readonly_dry_run_evidence.py \
  --output-json /tmp/phase4s_profile_segment_production_readonly_dry_run_evidence.json \
  --output-md /tmp/phase4s_profile_segment_production_readonly_dry_run_evidence.md
```

Future owner-approved execution must satisfy all gates before the tool calls the Phase 4R runner:

```bash
AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED=1 \
AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED=1 \
AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND=sqlalchemy \
AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL=<redacted-production-db-url> \
python3 tools/run_phase4s_profile_segment_template_production_readonly_dry_run_evidence.py \
  --read-only \
  --confirm-no-writes \
  --output-json /tmp/phase4s_profile_segment_production_readonly_dry_run_evidence.json \
  --output-md /tmp/phase4s_profile_segment_production_readonly_dry_run_evidence.md
```

The evidence gate must not use `DATABASE_URL`, staging DB env, test DB env, fixture/local_contract/demo data, or shared settings fallback as production evidence.

## Explicit Non-Claims

Phase 4S explicitly states:

- No create/update/delete.
- No production write canary.
- No route owner switch.
- No fallback removal.
- No `production_compat` change.
- No external calls.
- No production approval or cutover.
- Fixture/local_contract/demo evidence is not production dry-run evidence.

## Business Continuity

本 PR 只生成 Phase 4S production read-only dry-run evidence package/tool，不写生产，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。若 approval/config/read-only/no-write 条件不满足，必须输出 blocked evidence，不能伪造执行成功。

## Risk / Rollback

Rollback is deleting the Phase 4S evidence document, YAML, evidence tool, checker, and test. If only blocked evidence is produced, runtime is unaffected. If a future owner-approved read-only dry-run executes, no data rollback should be required because writes remain forbidden.

## Phase 4T Recommendation

Recommended next step: production read-only dry-run result review / route-owner switch readiness planning.

Phase 4T may review owner-approved read-only dry-run evidence or plan readiness criteria, but it must not write production data, switch route owner, remove fallback, or authorize a production write canary.
