# Phase 5V Media Upload Live Adapter Behind Flag

## Status

- phase_5v_media_upload_live_adapter_behind_flag
- live adapter code implemented behind explicit flags
- live upload disabled by default
- no production live upload
- no public media URL publication by default
- no destructive delete
- no raw file exposure
- no production owner switch
- no fallback removal
- no production_compat change
- no outbound send
- no canary approval
- delete_ready false

## Live Adapter Gates

The Phase 5V adapter may only reach the live gateway boundary when all gates are present:

- `AICRM_MEDIA_UPLOAD_LIVE_ADAPTER_ENABLED=1`
- `AICRM_MEDIA_UPLOAD_LIVE_UPLOAD_APPROVED=1`
- `AICRM_MEDIA_UPLOAD_CONFIG_REVIEWED=1`
- `AICRM_MEDIA_UPLOAD_PROVIDER_NAME`
- `AICRM_MEDIA_UPLOAD_PROVIDER_SECRET`
- explicit idempotency key
- runner confirm flag such as `--confirm-live-media-upload`

Default behavior remains blocked evidence with `live_provider_upload_executed=false`, `public_media_url_published=false`, `destructive_delete_executed=false`, and no production behavior change.

## Staging Evidence

The staging evidence runner supports a dry-run gate mode and an execute-live-staging mode. It defaults to blocked. Execute mode requires staging approval, config review, idempotency, and explicit confirm flags. Evidence records request hashes and redacts file metadata; it must not print provider secrets, tokens, raw files, or public provider URLs.

## Production Dry-Run Gate

The production dry-run gate never uploads to a provider. It verifies only that production readiness review is explicitly dry-run, no live upload is confirmed, no public publish is confirmed, and no delete is confirmed.

## Phase 5W Recommendation

Next bundle: `phase_5w_media_upload_staging_live_canary_evidence_bundle`.

Phase 5W may add a staging-only media upload canary evidence gate for a single approved test file. It must keep production upload, public publication, owner switch, fallback removal, and production_compat changes out of scope.

## Non-Goals

- no production live upload
- no public URL publication by default
- no raw file dump
- no destructive delete
- no route owner switch
- no fallback removal
- no production_compat change
- no payment, OAuth, WeCom, OpenClaw, MCP, timer, or automation execution
