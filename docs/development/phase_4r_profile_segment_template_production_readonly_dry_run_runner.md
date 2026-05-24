# Phase 4R Profile Segment Template Production Read-Only Dry-Run Runner

## Status

Phase 4R implements the production read-only dry-run runner only.

- Production read-only dry-run runner implementation.
- Runner is not run by this PR.
- No production repository enablement.
- No production route owner switch.
- No `production_compat` change.
- Legacy fallback retained.
- No writes.
- No external calls.
- `delete_ready`: false.

The runner is a future manual evidence tool for read-only profile-segment-template parity. It does not add, remove, or modify any business route and does not change the production facade owner.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Production dry-run / fallback boundary:

- `aicrm_next.integration_gateway`

Runner targets read-only parity for:

- `GET /api/admin/automation-conversion/profile-segment-templates/catalog`
- `GET /api/admin/automation-conversion/profile-segment-templates`
- `GET /api/admin/automation-conversion/profile-segment-templates/options`
- `GET /api/admin/automation-conversion/profile-segment-templates/{template_id}`

No business route is added, removed, or modified. Production facade enabled mode remains owned by the legacy `production_compat` fallback. The SQLAlchemy adapter exists but is not the production owner.

## Manual Execution Requirements

The runner defaults to blocked and is not run by CI. A future manual execution must set owner approval, production config review, SQLAlchemy backend, a production repository DB URL, and read-only/no-write flags:

```bash
AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED=1 \
AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED=1 \
AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND=sqlalchemy \
AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL=<redacted-production-db-url> \
python3 tools/run_phase4r_profile_segment_template_production_readonly_dry_run.py \
  --read-only \
  --confirm-no-writes \
  --output-json /tmp/phase4r_profile_segment_production_readonly_dry_run.json \
  --output-md /tmp/phase4r_profile_segment_production_readonly_dry_run.md
```

The runner must not use `DATABASE_URL`, staging DB env, test DB env, or shared settings fallback. Missing approval, config review, production DB URL, or read-only/no-write flags produces blocked evidence and does not connect to the DB.

## Read-Only Scope

Allowed operations:

- catalog read
- list read
- options read
- detail read when a template row is available

Forbidden operations:

- create
- update
- delete
- idempotency write
- audit write
- migration
- backfill
- workflow activation
- automation execution
- outbound send
- external calls

The runner exports counts, shape keys, source status, warning counts, and skipped details only. It does not dump raw row payloads, raw PII, secrets, audit payloads, or rollback payloads.

## Evidence Requirements

Future evidence must include:

- Redacted config summary.
- Read parity summary.
- Skipped details.
- Side-effect safety summary.
- Route owner unchanged evidence.
- `production_compat` retained evidence.
- Fallback retained evidence.
- Operator and timestamp.

Every report must show:

- `read_only: true`
- `writes_attempted: false`
- `route_owner_changed: false`
- `production_compat_changed: false`
- `fallback_retained: true`
- `raw_payload_exported: false`
- `pii_exported: false`

## Business Continuity

本 PR 只实现 Phase 4R production read-only dry-run runner，不执行 production dry-run，不启用 production repository，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。Runner 默认 blocked，只有未来在 owner approval + production config review + read-only/no-write flags 全部满足时才可手动执行。

Any future execution evidence must be collected in a separate owner-approved step. Production dry-run execution, production repository enablement, route ownership switch, fallback removal, production write dry-run, and production write canary remain unauthorized.

## Risk / Rollback

Rollback is deleting the Phase 4R runner, document, YAML, checker, and test. Because this PR does not change runtime route ownership, `production_compat`, fallback behavior, or schema, rollback does not affect current production automation operations.

## Phase 4S Recommendation

Recommended next step: production read-only dry-run execution evidence.

Phase 4S may collect owner-approved production read-only dry-run evidence. It must not write production data, must not switch route owner, must not remove fallback, and must not authorize a production write canary.
