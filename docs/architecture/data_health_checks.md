# Data Health Checks

PR #19 turns the existing table and identity governance checks into a Next-native admin diagnostic surface.

## API

- `GET /api/admin/data-health/summary`
- `GET /api/admin/data-health/checks`
- `GET /api/admin/data-health/checks/{check_id}`

Responses use only check metadata, counts, table names, and remediation hints. They must not expose raw payloads, phone numbers, OpenIDs, external user IDs, or other identity fields outside the existing identity boundary.

## Initial Checks

Green static checks:

- `identity_legacy_column_guard`
- `table_lifecycle_manifest_guard`
- `retired_table_runtime_reference_guard`

Live schema drift check:

- `schema_drift_guard`

Registered runtime data probes:

- `unionid_orphan_fact_guard`
- `identity_resolution_queue_backlog`
- `projection_freshness_customer_read_model`
- `broadcast_job_blocked_backlog`
- `external_effect_failed_retryable_backlog`
- `questionnaire_submission_without_user_guard`
- `payment_order_without_user_guard`
- `customer_360_freshness_guard`

The runtime probes are intentionally `not_applicable` in PR #19 until a production-safe read repository is attached. `schema_drift_guard` is also `not_applicable` when `DATABASE_URL` is absent; when a migrated database is available it compares `information_schema.columns` with the lifecycle manifest and fails on missing declared physical tables, unregistered live tables, retired physical tables, missing canonical owners, missing PII levels, or missing queue status enum metadata.

`customer_360_freshness_guard` registers Phase 4 freshness probes for `latest_identity_update`, `latest_order`, `latest_questionnaire`, `latest_message`, and `latest_projection_refresh`. Until a read-only production repository is attached, it reports only probe metadata and table names; it must not expose raw identity values or payloads.

## Status Semantics

- `ok`: check passed with current evidence.
- `warn`: check found a non-blocking operational risk.
- `fail`: check found a red condition that should block migration/release work.
- `not_applicable`: check is registered but does not yet have the required production-safe data probe.

## Next Steps

Follow-up PRs should attach read-only repositories for backlog, orphan-fact, and projection freshness checks, then add admin shell cards once the API can distinguish red/yellow/green with live data.
