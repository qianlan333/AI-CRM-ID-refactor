# Phase 5H WeCom Customer Contact Callback Adapter Contract

## Status

- status: phase_5h_wecom_customer_contact_adapter_contract
- no live WeCom callback cutover
- no production callback route owner switch
- no production external contact write
- no production identity mapping write
- no live customer sync
- no live tag write
- no outbound send
- no production_compat change
- no fallback removal
- no canary approval
- delete_ready false

This bundle is contract-only for `/wecom/external-contact/callback`. It documents the Next-side adapter boundary and fake/stub evidence shape while leaving the current production callback path, route ownership, fallback, and production compatibility behavior unchanged.

## Contract Scope

Covered:

- callback verification contract
- callback event receive contract
- event type normalization
- external_userid extraction and redaction policy
- follow_user_userid extraction
- event_key and idempotency key policy
- dry-run contact event handling
- dry-run identity mapping evidence
- dry-run customer read-model evidence
- error mapping
- replay / duplicate policy
- signature, token, and AESKey policy documentation

Not implemented:

- production callback cutover
- production signature/decrypt behavior change
- production contact write
- production identity map write
- production tag write
- customer sync
- outbound send
- OAuth callback
- payment/media/OpenClaw/MCP

## Adapter Contract

### verify_callback_contract(signature, timestamp, nonce, echostr)

- input fields: `signature`, `timestamp`, `nonce`, `echostr`
- output fields: `ok`, `result_status`, `verification_mode`, `live_callback_processed=false`, `production_write_executed=false`, `side_effect_safety`
- validation: all four fields must be present for a complete verification dry-run; signature comparison is documented only and does not alter production behavior
- error codes: `callback_config_missing`, `signature_invalid`, `decrypt_not_enabled`, `live_callback_not_enabled`, `adapter_unavailable`, `forbidden_in_production_without_approval`
- idempotency behavior: verification evidence is request-hash based and retry safe
- side_effect_safety: no decrypt by default, no callback cutover, no production write, no outbound send

### parse_external_contact_event(payload)

- input fields: encrypted or plain callback payload as contract reference
- output fields: `event_type`, `change_type`, `external_userid_redacted`, `follow_user_userid`, `event_key`, `request_hash`, `live_callback_processed=false`, `production_write_executed=false`
- validation: event payload must identify an external-contact event and provide enough fields for dry-run evidence
- error codes: `decrypt_not_enabled`, `event_type_unsupported`, `external_userid_missing`, `follow_user_userid_missing`, `adapter_unavailable`
- idempotency behavior: event parsing evidence uses deterministic `event_key`
- side_effect_safety: parsing does not write contact, identity mapping, tags, or read models

### normalize_external_contact_event(event)

- input fields: parsed event object with `event_type`, `change_type`, `external_userid`, `follow_user_userid`, `event_key`
- output fields: normalized event type, redacted external_userid, follow_user_userid, event_key, request_hash, result_status
- validation: supported external-contact events are normalized to stable names; unsupported event types return `event_type_unsupported`
- error codes: `event_type_unsupported`, `external_userid_missing`, `follow_user_userid_missing`
- idempotency behavior: normalized event keeps the same event_key
- side_effect_safety: normalization is pure contract evidence

### dry_run_record_contact_event(event, operator, idempotency_key)

- input fields: normalized event, `operator`, `idempotency_key`
- output fields: event_key, redacted external_userid, follow_user_userid, operator, idempotency_key, request_hash, result_status, `live_callback_processed=false`, `production_write_executed=false`
- validation: event_key, external_userid, follow_user_userid, operator, and idempotency_key are required
- error codes: `external_userid_missing`, `follow_user_userid_missing`, `idempotency_key_required`, `duplicate_event_key`, `forbidden_in_production_without_approval`
- idempotency behavior: same event_key returns duplicate/replay evidence; same idempotency key with different payload is conflict evidence
- side_effect_safety: no DB write and no production contact write

### dry_run_identity_mapping(event, operator, idempotency_key)

- input fields: normalized event, `operator`, `idempotency_key`
- output fields: event_key, redacted external_userid, follow_user_userid, mapping_evidence, request_hash, result_status, `live_callback_processed=false`, `production_write_executed=false`
- validation: same required fields as contact event dry-run
- error codes: `external_userid_missing`, `follow_user_userid_missing`, `idempotency_key_required`, `duplicate_event_key`, `forbidden_in_production_without_approval`
- idempotency behavior: same event_key returns replay evidence; same key with different payload returns conflict evidence
- side_effect_safety: no production identity mapping write and no customer read-model write

## Fake/Stub Behavior

- deterministic fake callback events
- no live WeCom request
- no secret/token/AESKey required
- no decrypt required by default
- no DB write
- no external_userid raw output
- returns contract evidence only

## Signature / Token / AESKey Policy

The contract documents verification inputs but does not change production signature or decrypt behavior. Fake/stub evidence never reads callback token, CorpID, secret, or AESKey. Decrypt is disabled by default, and any future decrypt behavior must be a separate, explicitly approved bundle.

## Error Mapping

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

## Idempotency / Replay Policy

- `event_key` is required for callback event dry-runs.
- `idempotency_key` is required for write-like dry-runs.
- Same `event_key` returns duplicate/replay evidence.
- Same idempotency key plus different payload returns conflict evidence.
- Retry is safe.
- There is no partial production side effect because live writes are disabled.

## Evidence / Audit Policy

Evidence fields:

- `adapter_mode`
- `live_callback_processed=false`
- `production_write_executed=false`
- `event_type`
- `event_key`
- `external_userid_redacted`
- `follow_user_userid`
- `operator`
- `idempotency_key`
- `request_hash`
- `result_status`
- `side_effect_safety`
- `timestamp`

## Production Behavior

Production behavior is unchanged. This bundle does not process live callback traffic, does not change callback signature/decrypt semantics, and does not create production contact, identity mapping, tag, customer sync, or read-model writes.

## Fallback Behavior

Legacy fallback remains retained. This bundle does not narrow or remove fallback behavior.

## Business Continuity

The current production callback route remains stable while the Next adapter contract becomes explicit. Operators get a deterministic fake/stub evidence path before any future fake runtime or live cutover discussion.

## Architecture Boundary

The boundary is `aicrm_next.integration_gateway` for callback contract and evidence shape. `aicrm_next.customer_read_model` and `aicrm_next.identity_contact` are referenced only for future read-model and identity mapping evidence; this PR does not change their runtime code. `wecom_ability_service` remains reference-only.

## Safety / Non-Goals

- no live WeCom callback cutover
- no production callback route owner switch
- no production external contact write
- no production identity mapping write
- no live customer sync
- no live tag write
- no outbound send
- no production_compat change
- no fallback removal
- no OAuth callback cutover
- no payment behavior
- no media upload
- no OpenClaw/MCP live call
- no timer or automation execution
- no destructive migration
- no canary approval
- delete_ready false

## Phase 5I Recommendation

- next: phase_5i_wecom_customer_contact_fake_stub_adapter_bundle
- route_family: /wecom/external-contact/callback
- no live WeCom callback cutover
- no production callback write
- no production owner switch

Phase 5I should implement the fake/stub callback adapter runtime only. It must keep live callback cutover, production callback writes, route ownership changes, fallback removal, and production_compat changes out of scope.
