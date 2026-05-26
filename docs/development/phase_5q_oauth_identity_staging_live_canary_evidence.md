# Phase 5Q OAuth Identity Staging Live Canary Evidence

## Status

- staging live canary evidence gate
- live staging OAuth call possible only with explicit approval
- no production OAuth callback cutover
- no production session write
- no production identity mapping write
- no production owner switch
- no fallback removal
- no production_compat change
- no outbound send
- no canary approval for production
- delete_ready false

## Staging canary gates

The staging canary runner is blocked by default. It may call the Phase 5P staging live evidence path only when every gate is present:

- `AICRM_OAUTH_IDENTITY_LIVE_ADAPTER_ENABLED=1`
- `AICRM_OAUTH_IDENTITY_LIVE_CALLBACK_APPROVED=1`
- `AICRM_OAUTH_IDENTITY_CONFIG_REVIEWED=1`
- `AICRM_PHASE5Q_OAUTH_IDENTITY_STAGING_CANARY_APPROVED=1`
- `AICRM_PHASE5Q_OAUTH_IDENTITY_STAGING_TARGET_APPROVED=1`
- OAuth app/client config required by the Phase 5P live adapter, never printed
- `--execute-staging-canary`
- `--confirm-live-oauth-call`
- `--confirm-staging-only`
- `--confirm-approved-target`
- `--idempotency-key`
- `--state`
- `--code` or `--fake-safe-code`

## Target safety

- one explicit staging callback attempt only
- approved target only
- no production callback URL
- redacted state, code, and token evidence
- no batch replay
- no production session write
- no production identity write
- no raw secret or token output

## Cleanup / rollback

No token persistence is enabled by this bundle. Cleanup and rollback evidence is review-only. Production cleanup is not authorized, and any later production cleanup requires a separate approval bundle.

## Production readiness

The production readiness review only checks whether acceptable staging evidence exists. It never calls an OAuth provider, never cuts over a production callback route, never writes a production session, and never writes production identity mapping.

Phase 5R may be production canary readiness only:

- next: phase_5r_oauth_identity_production_canary_readiness_bundle
- route_family: /api/h5/wechat/oauth*
- no production callback cutover
- no production session write
