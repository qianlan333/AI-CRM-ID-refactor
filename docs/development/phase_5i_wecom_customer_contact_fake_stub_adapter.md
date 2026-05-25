# Phase 5I WeCom Customer Contact Fake/Stub Adapter

## Status

- status: `phase_5i_wecom_customer_contact_fake_stub_adapter`
- bundle type: `phase_5_external_adapter_fake_stub_runtime_and_readiness_bundle`
- route family: `/wecom/external-contact/callback`
- capability owner: `aicrm_next.integration_gateway`
- fake/stub callback adapter runtime implemented
- no live WeCom callback cutover
- no production callback route owner switch
- no production signature/decrypt behavior change
- no production external contact write
- no production identity mapping write
- no live customer sync
- no live tag write
- no outbound send
- no production_compat change
- no fallback removal
- no canary approval
- `delete_ready: false`

## Implemented Fake/Stub Methods

The Phase 5I runtime implements the Phase 5H contract under `aicrm_next.integration_gateway`:

- `verify_callback_contract(signature, timestamp, nonce, echostr)`
- `parse_external_contact_event(payload)`
- `normalize_external_contact_event(event)`
- `dry_run_record_contact_event(event, operator, idempotency_key)`
- `dry_run_identity_mapping(event, operator, idempotency_key)`

The adapter returns deterministic fake/stub evidence only. It does not decrypt production callback payloads, read WeCom secrets, read CorpID, use tokens, call a live client, write DB state, update contact records, update identity mappings, sync customers, write tags, or send messages.

## Fake/Stub Callback Behavior

- Deterministic fake callback events cover `add_external_contact` and `edit_external_contact`.
- Payload parsing accepts common callback field names and normalizes into `event_type`, `change_type`, `event_key`, `external_userid_redacted`, and `follow_user_userid`.
- Raw `external_userid` is not returned in evidence.
- Callback verification is contract-only and does not change production signature/decrypt behavior.
- `live_callback_processed=false`, `production_write_executed=false`, and every production side-effect flag remains false.
- Production mode may return contract or dry-run evidence only and must not claim a real production outcome.

## Idempotency And Replay Policy

- `event_key` is required for callback event dry-runs. If absent, the fake/stub adapter derives a deterministic event key from the normalized event.
- `idempotency_key` is required for write-like dry-runs.
- Same idempotency key with the same payload returns replay evidence.
- Same idempotency key with a different payload returns a conflict.
- Same event key returns duplicate/replay evidence.
- Retries are safe because live callback processing and production writes are disabled.

## Error Mapping

The runtime and checker require these error codes:

- `callback_config_missing`
- `signature_invalid`
- `decrypt_not_enabled`
- `event_type_unsupported`
- `external_userid_missing`
- `follow_user_userid_missing`
- `idempotency_key_required`
- `duplicate_event_key`
- `live_callback_not_enabled`
- `adapter_unavailable`
- `forbidden_in_production_without_approval`

## Readiness Packages

Staging fake/stub smoke runner:

- `tools/run_phase5i_wecom_customer_contact_fake_stub_staging_smoke.py`
- default blocked unless `AICRM_PHASE5I_WECOM_CONTACT_STAGING_SMOKE_APPROVED=1`
- uses fake/stub adapter only
- no network, token, AESKey, live callback, DB write, or production route owner change

Production fake/stub dry-run runner:

- `tools/run_phase5i_wecom_customer_contact_fake_stub_production_dry_run.py`
- default blocked unless approvals and `--dry-run --confirm-no-live-callback` are present
- never processes live production callback
- never writes production external contact or identity mapping state

## Production Behavior

Production behavior remains unchanged. This bundle does not switch `/wecom/external-contact/callback` ownership, does not change production signature/decrypt behavior, does not narrow fallback, and does not update `production_compat`.

## Phase 5J Recommendation

Next bundle:

- `phase_5j_wecom_customer_contact_live_callback_adapter_behind_flag_bundle`
- route family: `/wecom/external-contact/callback`

Phase 5J should add live callback adapter code behind explicit flags only. It must keep live callback processing disabled by default, require approval gates, and continue to avoid production callback owner switch, fallback removal, and production_compat changes.
