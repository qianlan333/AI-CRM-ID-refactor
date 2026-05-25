# Phase 5N OAuth Identity Adapter Contract

## Status

- status: phase_5n_oauth_identity_adapter_contract
- no live OAuth callback cutover
- no production callback route owner switch
- no production OAuth token exchange
- no production session write
- no production identity write
- no outbound send
- no production_compat change
- no fallback removal
- no canary approval
- delete_ready false

This bundle is contract-only for `/api/h5/wechat/oauth*`. It documents the Next-side OAuth identity adapter boundary and fake/stub evidence shape while leaving the current production OAuth transport, route ownership, fallback, and production compatibility behavior unchanged.

## Contract Scope

Covered:

- OAuth authorize URL contract
- OAuth callback payload shape
- callback state normalization
- openid and unionid extraction / redaction policy
- OAuth event key and idempotency key policy
- dry-run identity evidence
- dry-run session identity evidence
- error mapping
- replay / duplicate policy
- AppID, AppSecret, token exchange, and redirect URI policy documentation

Not implemented:

- production OAuth callback cutover
- production callback route owner switch
- production token exchange
- production session write
- production identity mapping write
- payment/media/WeCom/OpenClaw/MCP live call
- outbound send
- timer or automation execution
- production_compat behavior change
- fallback removal

## Adapter Contract

### build_oauth_authorize_url_contract(slug, state, redirect_uri, scope)

- input fields: `slug`, `state`, `redirect_uri`, `scope`
- output fields: `ok`, `result_status`, `authorize_url_evidence`, `live_oauth_call_executed=false`, `live_callback_processed=false`, `side_effect_safety`
- validation: state and redirect URI must be present for a complete authorize evidence shape; redirect URI validation is contract-only
- error codes: `oauth_config_missing`, `state_missing`, `redirect_uri_invalid`, `live_oauth_callback_not_enabled`, `adapter_unavailable`, `forbidden_in_production_without_approval`
- idempotency behavior: authorize evidence is request-hash based and retry safe
- side_effect_safety: no token exchange, no network call, no session write, no production identity write

### parse_oauth_callback_contract(code, state, openid, unionid)

- input fields: `code`, `state`, optional fake/stub `openid`, optional fake/stub `unionid`
- output fields: `oauth_event_type`, `oauth_event_key`, `openid_redacted`, `unionid_redacted`, `state`, `request_hash`, `live_oauth_call_executed=false`, `live_callback_processed=false`
- validation: callback state is required; code is documented but not exchanged in this contract bundle; openid is required for fake/stub identity evidence
- error codes: `oauth_code_missing`, `state_missing`, `state_invalid`, `openid_missing`, `token_exchange_not_enabled`, `adapter_unavailable`
- idempotency behavior: parsed callback evidence uses a deterministic OAuth event key
- side_effect_safety: parsing does not call WeChat, exchange code, write session, or write identity

### normalize_oauth_identity_event(event)

- input fields: parsed OAuth event with `oauth_event_type`, `state`, `openid`, `unionid`, `oauth_event_key`
- output fields: normalized event type, redacted openid, redacted unionid, state, oauth_event_key, request_hash, result_status
- validation: supported OAuth callback events normalize to stable names; unsupported events return `state_invalid` or `adapter_unavailable`
- error codes: `state_missing`, `state_invalid`, `openid_missing`
- idempotency behavior: normalized event keeps the same OAuth event key
- side_effect_safety: normalization is pure contract evidence

### dry_run_record_oauth_identity(event, operator, idempotency_key)

- input fields: normalized event, `operator`, `idempotency_key`
- output fields: oauth_event_key, openid_redacted, unionid_redacted, state, operator, idempotency_key, request_hash, result_status, `production_identity_write_executed=false`
- validation: oauth_event_key, state, openid, operator, and idempotency_key are required
- error codes: `openid_missing`, `state_missing`, `idempotency_key_required`, `duplicate_oauth_event_key`, `forbidden_in_production_without_approval`
- idempotency behavior: same event key returns duplicate/replay evidence; same idempotency key with different payload returns conflict evidence
- side_effect_safety: no DB write and no production identity write

### dry_run_session_identity_evidence(event, operator, idempotency_key)

- input fields: normalized event, `operator`, `idempotency_key`
- output fields: oauth_event_key, redacted identity fields, session evidence, request_hash, result_status, `production_session_write_executed=false`
- validation: same required fields as identity dry-run
- error codes: `state_missing`, `openid_missing`, `idempotency_key_required`, `duplicate_oauth_event_key`, `forbidden_in_production_without_approval`
- idempotency behavior: same event key returns replay evidence; same key with different payload returns conflict evidence
- side_effect_safety: no production session write and no production identity mapping write

## Fake/Stub Behavior

- deterministic fake OAuth callback events
- no live WeChat OAuth request
- no AppID or AppSecret required
- no token exchange
- no network call
- no DB write
- no session write
- no raw openid or unionid output
- returns contract evidence only

## AppID / AppSecret / Token Policy

The contract documents OAuth callback inputs but does not change production OAuth signature, redirect, token exchange, or session behavior. Fake/stub evidence never reads AppID, AppSecret, access token, refresh token, or production callback configuration. Any future live token exchange must be a separate explicitly approved bundle behind flags.

## Error Mapping

- `oauth_config_missing`
- `oauth_code_missing`
- `state_missing`
- `state_invalid`
- `redirect_uri_invalid`
- `openid_missing`
- `idempotency_key_required`
- `duplicate_oauth_event_key`
- `live_oauth_callback_not_enabled`
- `token_exchange_not_enabled`
- `adapter_unavailable`
- `forbidden_in_production_without_approval`

## Idempotency / Replay Policy

- `oauth_event_key` is required for callback event dry-runs.
- `idempotency_key` is required for write-like dry-runs.
- Same OAuth event key returns duplicate/replay evidence.
- Same idempotency key plus different payload returns conflict evidence.
- Retry is safe.
- There is no partial production side effect because live writes and token exchange are disabled.

## Evidence / Audit Policy

Evidence fields:

- `adapter_mode`
- `live_oauth_call_executed=false`
- `live_callback_processed=false`
- `production_session_write_executed=false`
- `production_identity_write_executed=false`
- `oauth_event_type`
- `oauth_event_key`
- `openid_redacted`
- `unionid_redacted`
- `state`
- `operator`
- `idempotency_key`
- `request_hash`
- `result_status`
- `side_effect_safety`
- `timestamp`

## Production Behavior

Production behavior is unchanged. This bundle does not process live OAuth callbacks, does not exchange OAuth codes, does not write production session identity, and does not change production callback ownership or production_compat behavior.

## Fallback Behavior

Legacy fallback remains retained. This bundle does not narrow or remove fallback behavior.

## Business Continuity

The current production OAuth route remains stable while the Next adapter contract becomes explicit. Operators get a deterministic fake/stub evidence path before any future fake runtime or live cutover discussion.

## Architecture Boundary

The boundary is `aicrm_next.integration_gateway` for OAuth identity contract and evidence shape. Existing `aicrm_next.questionnaire.oauth` and legacy transport are referenced only for route-family context; this PR does not change their runtime code.

## Safety / Non-Goals

- no live OAuth callback cutover
- no production callback route owner switch
- no production token exchange
- no production session write
- no production identity write
- no outbound send
- no production_compat change
- no fallback removal
- no payment behavior
- no media upload
- no WeCom live call
- no OpenClaw/MCP live call
- no timer or automation execution
- no destructive migration
- no canary approval
- delete_ready false

## Phase 5O Recommendation

- next: phase_5o_oauth_identity_fake_stub_adapter_bundle
- route_family: /api/h5/wechat/oauth*
- no live OAuth callback cutover
- no production session write
- no production owner switch

Phase 5O should implement the fake/stub OAuth identity adapter runtime only. It must keep live OAuth callback cutover, production session writes, route ownership changes, fallback removal, and production_compat changes out of scope.
