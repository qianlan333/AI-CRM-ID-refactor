# Phase 5O OAuth Identity Fake/Stub Adapter

## Status

- phase_5o_oauth_identity_fake_stub_adapter
- fake/stub runtime implemented
- no live OAuth callback cutover
- no production token exchange
- no production session write
- no production identity write
- no production owner switch
- no fallback removal
- no production_compat change
- no canary approval
- delete_ready false

## Implemented fake/stub methods

- `build_oauth_authorize_url_contract`
- `parse_oauth_callback_contract`
- `normalize_oauth_identity_event`
- `dry_run_record_oauth_identity`
- `dry_run_session_identity_evidence`

## Readiness packages

- staging fake/stub smoke package, blocked unless `AICRM_PHASE5O_OAUTH_IDENTITY_STAGING_SMOKE_APPROVED=1`
- production fake/stub dry-run package, blocked unless approval/config env and `--dry-run --confirm-no-live-oauth-callback` are present

## Boundaries

- no live OAuth callback cutover
- no WeChat token exchange
- no AppID/AppSecret requirement
- no network
- no DB write
- no production session write
- no production identity mapping write
- no outbound send
- no production_compat change

## Idempotency

Write-like dry-runs require an idempotency key. Same key and same payload returns replay evidence. Same key with different payload returns conflict. Same OAuth event key returns duplicate event replay. No partial production side effect exists because live callback processing and writes are disabled.

## Production behavior

Production behavior is unchanged. Fake/stub evidence must not be treated as real OAuth success or production identity/session success.

## Phase 5P recommendation

- next: phase_5p_oauth_identity_live_adapter_behind_flag_bundle
- route_family: /api/h5/wechat/oauth*
- live callback disabled by default
- explicit owner approval required before any live OAuth callback/token exchange path
