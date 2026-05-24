# Phase 4K Profile Segment Template Local Parity Harness

## Status

Phase 4K implements a local test DB parity harness only.

- No production data connection.
- No production repository enablement.
- No production route owner switch.
- No `production_compat` change.
- Legacy fallback retained.
- No staging or production smoke execution.
- No real external calls.
- `delete_ready`: false.

The harness targets the Phase 4I opt-in SQLAlchemy repository adapter for local parity checks. It does not change runtime registration or production ownership for `/api/admin/automation-conversion/profile-segment-templates*`.

## How To Run

The harness requires an explicit local test DB URL:

```bash
AICRM_NEXT_TEST_DATABASE_URL=sqlite+pysqlite:////tmp/phase4k_profile_segment_test.db \
  python3 tools/run_phase4k_profile_segment_template_local_parity.py \
  --output-json /tmp/phase4k_profile_segment_template_local_parity.json \
  --output-md /tmp/phase4k_profile_segment_template_local_parity.md
```

Safety guard:

- `AICRM_NEXT_TEST_DATABASE_URL` is required.
- The database URL or database name must include `test`, `local`, `tmp`, or `dev`.
- The harness does not fall back to `DATABASE_URL`.
- The harness does not use production repository config.
- SQLite local test URLs can create the required local harness tables.
- Non-SQLite URLs must already contain the required local test tables; otherwise the harness fails with a clear error.

The JSON and Markdown outputs report `ok`, DB URL safety, test counts, case details, side-effect safety, `production_data_used: false`, `route_owner_changed: false`, and `production_compat_changed: false`.

## Test Matrix

Read parity cases:

- catalog
- list
- options
- detail

Write parity cases:

- create idempotency replay
- create idempotency conflict
- duplicate template name/code
- update existing template
- update missing template
- invalid payload
- dangerous field rejection
- audit log shape
- rollback payload shape

The harness creates only safe local test rows using the `phase4k_local_parity_` code and idempotency-key prefix plus the `phase4k_local_parity_operator` operator. It cannot treat fixture/local_contract/demo results as production parity success.

## Business Continuity

This harness does not affect current production behavior. It does not connect production data, enable production repository traffic, switch production route ownership, narrow `production_compat`, remove fallback, execute staging/prod smoke, or trigger external side effects. Rollback is deleting the harness document, YAML, tool, checker, and tests.

## Phase 4L Recommendation

After owner approval and a passing local test DB parity run, Phase 4L may plan staging smoke. It must not connect production data, switch production route owner, remove fallback, or authorize a production write canary.
