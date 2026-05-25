# Phase 5F WeCom Tag Production Live Canary Execution

## Status

- status: phase_5f_wecom_tag_production_live_canary_execution_bundle
- bundle_type: phase_5_external_adapter_production_live_canary_execution_bundle
- route_family: /api/admin/wecom/tags*
- capability_owner: aicrm_next.customer_tags
- production live canary execution tooling
- default blocked
- one target / one tag only
- explicit approval required
- cleanup runner included
- no production owner switch
- no fallback removal
- no production_compat change
- no outbound send
- no bulk target
- delete_ready false

## Production Canary Gates

The production canary runner is blocked by default. It may execute only one live `mark_tags_live` operation after every gate below is satisfied:

- Phase 5E readiness evidence JSON
- Phase 5D staging evidence JSON
- production canary approval
- target approval
- rollback owner approval
- cleanup strategy approval
- live adapter enabled
- live call approved
- config reviewed
- CorpID and agent secret available through the approved secret channel
- explicit idempotency key
- `--confirm-production-live-wecom-call`
- `--confirm-single-approved-target`
- `--confirm-single-approved-tag`
- `--confirm-rollback-owner-approved`
- `--confirm-no-batch-target`
- `--confirm-no-outbound-send`

## Target Safety

- Single external_userid.
- Single tag_id.
- No segment target.
- No customer pool target.
- No batch target.
- Evidence redacts external_userid.
- Raw tokens and raw secrets are never printed.
- No outbound send, OAuth callback, payment, media upload, OpenClaw/MCP call, timer execution, or automation execution is allowed.

## Cleanup / Rollback

- Cleanup runner: `tools/run_phase5f_wecom_tag_production_canary_cleanup.py`.
- Cleanup is blocked by default.
- Cleanup can only use Phase 5F canary evidence from the same target and same tag.
- Cleanup evidence is required.
- Cleanup requires explicit rollback owner approval and cleanup confirmation flags.
- Batch cleanup and automatic cleanup are forbidden.

## Phase 5G Recommendation

- next: phase_5g_wecom_tag_family_acceptance_bundle
- route_family: /api/admin/wecom/tags*
- confirm whether production canary evidence passed or remained blocked
- no route owner switch unless a later Phase 6/7 explicit package authorizes it
