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

Registered runtime data probes:

- `unionid_orphan_fact_guard`
- `identity_resolution_queue_backlog`
- `projection_freshness_customer_read_model`
- `broadcast_job_blocked_backlog`
- `external_effect_failed_retryable_backlog`
- `questionnaire_submission_without_user_guard`
- `payment_order_without_user_guard`

The runtime probes are intentionally `not_applicable` in PR #19 until a production-safe read repository is attached. This prevents the admin health API from pretending it has live queue or orphan-fact evidence when it does not.

## Status Semantics

- `ok`: check passed with current evidence.
- `warn`: check found a non-blocking operational risk.
- `fail`: check found a red condition that should block migration/release work.
- `not_applicable`: check is registered but does not yet have the required production-safe data probe.

## Next Steps

Follow-up PRs should attach read-only repositories for backlog, orphan-fact, and projection freshness checks, then add admin shell cards once the API can distinguish red/yellow/green with live data.
