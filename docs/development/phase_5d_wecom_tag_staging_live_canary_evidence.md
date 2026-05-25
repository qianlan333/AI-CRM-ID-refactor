# Phase 5D WeCom Tag Staging Live Canary Evidence

## Status

- status: phase_5d_wecom_tag_staging_live_canary_evidence
- bundle_type: phase_5_external_adapter_staging_live_canary_evidence_bundle
- route_family: /api/admin/wecom/tags*
- capability_owner: aicrm_next.customer_tags
- staging live canary evidence gate is added
- live staging call is possible only with explicit approval, reviewed config, approved target, idempotency, and confirm flags
- no production live call
- no production tag write
- no production owner switch
- no fallback removal
- no production_compat change
- no outbound send
- no production canary approval
- delete_ready false

## Staging Canary Gates

The Phase 5D canary runner is blocked by default. It may call only the Phase 5C staging live evidence path, and only after every gate below is present:

- `AICRM_WECOM_TAG_LIVE_ADAPTER_ENABLED=1`
- `AICRM_WECOM_TAG_LIVE_CALL_APPROVED=1`
- `AICRM_WECOM_TAG_CONFIG_REVIEWED=1`
- `AICRM_PHASE5D_WECOM_TAG_STAGING_CANARY_APPROVED=1`
- `AICRM_PHASE5D_WECOM_TAG_STAGING_CANARY_TARGET_APPROVED=1`
- `AICRM_WECOM_TAG_CORP_ID` present
- `AICRM_WECOM_TAG_AGENT_SECRET` present through the approved secret channel
- `--execute-staging-canary`
- `--confirm-live-wecom-call`
- `--confirm-staging-only`
- `--confirm-approved-target`
- `--idempotency-key <key>`
- `--external-userid <external_userid>`
- `--tag-id <tag_id>`

If any gate is missing, the runner emits blocked evidence and does not call WeCom.

## Target Safety

- Single staging target only by default.
- Batch targets are rejected by default.
- The target must be explicitly approved before execution.
- Evidence redacts `external_userid`.
- Raw tokens and raw secrets are never printed.
- No batch `mark_tag` operation is introduced in this bundle.
- No message send, OAuth callback, payment, media upload, OpenClaw/MCP call, timer execution, or automation execution is allowed.

## Cleanup / Rollback

Cleanup is evidence-only in this bundle. If a staging tag needs to be removed after a later approved live canary, cleanup must be run as a separately approved staging action using the Phase 5C guarded unmark shape. There is no automatic cleanup and no production cleanup in Phase 5D.

Rollback for this bundle is to remove the Phase 5D docs, checker, and runners. Production behavior is unchanged because the bundle does not switch route ownership, change fallback behavior, or enable production writes.

## Production Readiness

The production readiness runner is review-only. It checks whether staging canary evidence exists and keeps these fields false:

- production live call executed
- production tag write executed
- route owner changed
- production_compat unchanged
- fallback retained

Phase 5D does not authorize a production canary. Phase 5E may prepare production canary planning/readiness only, with separate approval.

## Next Bundle Recommendation

- next: phase_5e_wecom_tag_production_canary_readiness_bundle
- route_family: /api/admin/wecom/tags*
