# Phase 5P OAuth Identity Live Adapter Behind Flag

## Status

- live adapter implemented behind explicit flag
- live OAuth callback disabled by default
- no production callback cutover
- no production owner switch
- no production session write
- no production identity write
- no fallback removal
- no production_compat change
- no outbound send
- no canary approval
- delete_ready false

## Live adapter gates

Live OAuth code may only proceed when all required gates are present:

- `AICRM_OAUTH_IDENTITY_LIVE_ADAPTER_ENABLED=1`
- `AICRM_OAUTH_IDENTITY_LIVE_CALLBACK_APPROVED=1`
- `AICRM_OAUTH_IDENTITY_CONFIG_REVIEWED=1`
- `AICRM_OAUTH_IDENTITY_APP_ID`
- `AICRM_OAUTH_IDENTITY_APP_SECRET` or a future safe secret provider
- explicit idempotency key for code exchange
- `--confirm-live-oauth-callback` for runner paths

Default responses have `live_oauth_call_executed=false`, `live_callback_processed=false`, `code_exchange_executed=false`, `production_session_write_executed=false`, and `production_identity_write_executed=false`.

## Staging evidence

The staging runner supports dry-run gate mode and execute-live-staging mode. It is blocked by default and requires explicit staging approval before live execution. Evidence redacts identity fields and never prints secrets or tokens.

## Production dry-run gate

The production dry-run gate checks readiness only. It never calls OAuth, never exchanges code, never writes session identity, and never writes identity mapping.

## Production behavior

Production behavior remains unchanged. This PR does not change callback route ownership, production_compat behavior, fallback behavior, or the legacy production OAuth transport.

## Phase 5Q recommendation

- next: phase_5q_oauth_identity_staging_live_canary_evidence_bundle
- route_family: /api/h5/wechat/oauth*
- staging-only evidence gate
- no production callback cutover
