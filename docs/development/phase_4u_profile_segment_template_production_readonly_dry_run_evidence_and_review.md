# Phase 4U Profile Segment Template Production Read-Only Dry-Run Evidence And Review

## Status

Phase 4U combines a production read-only dry-run execution evidence attempt with evidence review and next readiness decision.

- Production read-only dry-run execution evidence attempt.
- Evidence review / route-owner switch readiness decision.
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

Production dry-run evidence / fallback boundary:

- `aicrm_next.integration_gateway`

Read-only evidence only for:

- `GET /api/admin/automation-conversion/profile-segment-templates/catalog`
- `GET /api/admin/automation-conversion/profile-segment-templates`
- `GET /api/admin/automation-conversion/profile-segment-templates/options`
- `GET /api/admin/automation-conversion/profile-segment-templates/{template_id}`

## Execution Result

Current result:

- `not_executed_missing_approval`

The current Phase 4U evidence attempt is blocked because owner approval, production config review, production DB URL, and read-only/no-write execution conditions are not present in this PR. The lower Phase 4R runner is not called, no DB connection is made, and production read-only dry-run is not claimed as successful.

Allowed result statuses:

- `not_executed_missing_approval`
- `not_executed_config_not_reviewed`
- `not_executed_missing_production_db`
- `not_executed_read_only_flags_missing`
- `not_executed_safety_failed`
- `read_only_dry_run_executed`

## Required Evidence Fields

Every Phase 4U report must include:

- Command attempted or not-attempted reason.
- Approval flags summary.
- Production config reviewed summary.
- DB URL redaction summary.
- Lower runner called true/false.
- Read-only dry-run executed true/false.
- Read parity summary if executed.
- Skipped details.
- Side-effect safety summary.
- `writes_attempted: false`.
- `route_owner_changed: false`.
- `production_compat_changed: false`.
- `fallback_retained: true`.
- Operator.
- Timestamp.

Reports must redact DB credentials, must not export raw payloads, and must not export raw PII. Fixture, local_contract, demo, local test DB, and staging-only evidence cannot be treated as production read-only dry-run success.

## Evidence Tool

Default blocked evidence:

```bash
python3 tools/run_phase4u_profile_segment_template_production_readonly_dry_run_evidence_and_review.py \
  --output-json /tmp/phase4u_profile_segment_template_production_readonly_dry_run_evidence_and_review.json \
  --output-md /tmp/phase4u_profile_segment_template_production_readonly_dry_run_evidence_and_review.md
```

Future owner-approved read-only execution must satisfy all gates before the tool calls Phase 4R:

```bash
AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED=1 \
AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED=1 \
AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND=sqlalchemy \
AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL=<redacted-production-db-url> \
python3 tools/run_phase4u_profile_segment_template_production_readonly_dry_run_evidence_and_review.py \
  --read-only \
  --confirm-no-writes \
  --output-json /tmp/phase4u_profile_segment_template_production_readonly_dry_run_evidence_and_review.json \
  --output-md /tmp/phase4u_profile_segment_template_production_readonly_dry_run_evidence_and_review.md
```

If any gate is missing, the tool must not call the lower runner and must emit blocked evidence.

## Review / Readiness Decision

Current readiness:

- `route_switch_ready: false`
- `production_repository_route_enablement_ready: false`
- `fallback_removal_ready: false`
- `production_write_ready: false`

Current blockers:

- Phase 4U evidence attempt is blocked at `not_executed_missing_approval`.
- Production read-only dry-run has not executed.
- Read parity summary is not present because execution did not start.

If evidence is blocked-only:

- Production read-only dry-run has not executed.
- Route-owner switch readiness remains not ready.
- Production repository route enablement remains unauthorized.
- Fallback removal remains unauthorized.
- Next step remains owner-approved read-only dry-run execution.

If evidence executes in a future owner-approved run, the review must still explicitly state:

- Read-only only.
- No create/update/delete.
- No production write.
- No route owner switch.
- No fallback removal.
- No `production_compat` change.
- Read parity result.
- Blockers if any.

## Business Continuity

本 PR 只生成 Phase 4U owner-approved production read-only dry-run execution evidence attempt + evidence review，不写生产，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。若 approval/config/read-only/no-write 条件不满足，必须输出 blocked evidence，不能伪造执行成功。

## Risk / Rollback

Rollback is deleting the Phase 4U evidence/review document, YAML, tool, checker, and test. If only blocked evidence is produced, runtime is unaffected. If a future owner-approved read-only dry-run executes, no data rollback should be required because writes remain forbidden.

## Phase 4V Recommendation

If Phase 4U remains blocked evidence, Phase 4V should continue owner-approved production read-only dry-run execution evidence. If Phase 4U has actual execution and read parity passed, Phase 4V may prepare a route-owner switch readiness package, but must not directly switch route owner.
