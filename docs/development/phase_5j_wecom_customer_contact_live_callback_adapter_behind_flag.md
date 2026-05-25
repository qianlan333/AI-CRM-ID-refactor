# Phase 5J WeCom Customer Contact Live Callback Adapter Behind Flag

## Status

- status: `phase_5j_wecom_customer_contact_live_callback_adapter_behind_explicit_flag`
- bundle type: `phase_5_external_adapter_live_adapter_behind_flag_bundle`
- route family: `/wecom/external-contact/callback`
- live callback adapter code implemented behind explicit flags
- live callback processing disabled by default
- no production callback cutover
- no production callback route owner switch
- no production contact write by default
- no production identity mapping write by default
- no live customer sync by default
- no live tag write
- no outbound send
- no production_compat change
- no fallback removal
- no canary approval
- `delete_ready: false`

## Live Callback Adapter Gates

The live adapter may only proceed past blocked evidence when all gates are present:

- `AICRM_WECOM_CONTACT_CALLBACK_LIVE_ADAPTER_ENABLED=1`
- `AICRM_WECOM_CONTACT_CALLBACK_LIVE_PROCESSING_APPROVED=1`
- `AICRM_WECOM_CONTACT_CALLBACK_CONFIG_REVIEWED=1`
- `AICRM_WECOM_CONTACT_CALLBACK_CORP_ID` present
- `AICRM_WECOM_CONTACT_CALLBACK_TOKEN` present
- `AICRM_WECOM_CONTACT_CALLBACK_AES_KEY` present
- explicit `idempotency_key` for write-like processing
- runner path uses `--confirm-live-wecom-callback`

If any gate is missing, the adapter returns blocked evidence with `live_callback_processed=false` and all production write fields false.

## Adapter Boundary

Runtime files:

- `aicrm_next/integration_gateway/wecom_contact_callback_live_adapter.py`
- `aicrm_next/integration_gateway/wecom_contact_callback_live_gateway.py`
- `aicrm_next/integration_gateway/wecom_contact_callback_application.py`

The gateway boundary is intentionally named and disabled by default. This bundle does not import random legacy Flask runtime modules and does not add new `wecom_ability_service` business logic.

## Staging Evidence

Runner:

- `tools/run_phase5j_wecom_customer_contact_live_callback_staging_evidence.py`

Modes:

- `--dry-run-live-gate`: checks gates only and never processes a live callback.
- `--execute-live-staging`: may call only the Phase 5J live adapter path if all approvals and `--confirm-live-wecom-callback` are present.

Evidence redacts `external_userid`, does not print secret/token/AESKey values, and never sends messages.

## Production Dry-Run Gate

Runner:

- `tools/run_phase5j_wecom_customer_contact_live_callback_production_dry_run_gate.py`

This runner verifies production readiness gates only. It does not process a live production callback, write production contact state, write production identity mapping state, change route ownership, change production_compat, or remove fallback.

## Idempotency Policy

- `idempotency_key` is required for live write-like callback processing.
- Same key plus same payload returns replay evidence.
- Same key plus different payload returns conflict evidence.
- Blocked requests have no partial production side effect.

## Phase 5K Recommendation

Next bundle:

- `phase_5k_wecom_customer_contact_staging_live_callback_canary_evidence_bundle`
- route family: `/wecom/external-contact/callback`

Phase 5K should be staging-only canary evidence with approved target/event guardrails. It must not switch production callback ownership or enable production callback cutover.
