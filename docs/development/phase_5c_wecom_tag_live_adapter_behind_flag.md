# Phase 5C WeCom Tag Live Adapter Behind Flag

## Status

- status: phase_5c_wecom_tag_live_adapter_behind_explicit_flag
- bundle type: phase_5_external_adapter_live_adapter_behind_flag_bundle
- route family: /api/admin/wecom/tags*
- capability owner: aicrm_next.customer_tags
- live adapter implemented behind explicit flag
- live call disabled by default
- no production owner switch
- no fallback removal
- no production_compat change
- no outbound send
- no canary approval
- delete_ready false

## Live Adapter Gates

The live adapter code may exist in Phase 5C, but it remains blocked unless every explicit gate is present:

- `AICRM_WECOM_TAG_LIVE_ADAPTER_ENABLED=1`
- `AICRM_WECOM_TAG_LIVE_CALL_APPROVED=1`
- `AICRM_WECOM_TAG_CONFIG_REVIEWED=1`
- `AICRM_WECOM_TAG_CORP_ID` is present
- `AICRM_WECOM_TAG_AGENT_SECRET` is present
- write-like methods include `idempotency_key`
- runner execution includes `--confirm-live-wecom-call`

If any gate is absent, responses return blocked evidence with `live_call_executed=false`, `mark_tag_executed=false`, `unmark_tag_executed=false`, `token_used=false`, and `network_call_executed=false`.

Production guard: `AICRM_NEXT_ENV=production` does not relax any gate. Phase 5C does not switch production route ownership, does not alter production_compat, and does not treat fake/stub evidence as external success.

## Staging Evidence

`tools/run_phase5c_wecom_tag_live_staging_evidence.py` supports:

- `--dry-run-live-gate`: checks the live gate set and never calls WeCom.
- `--execute-live-staging`: may call the live list-tags path only when all live gates, `AICRM_PHASE5C_WECOM_TAG_STAGING_LIVE_APPROVED=1`, and `--confirm-live-wecom-call` are present.

The staging evidence records external_userid redaction policy, side_effect_safety, idempotency key, request hash, approval/config flags, and timestamp. It never sends messages and never touches OAuth, payment, media, OpenClaw/MCP, timer, or automation execution.

## Production Dry-Run Gate

`tools/run_phase5c_wecom_tag_live_production_dry_run_gate.py` is readiness-only. It requires:

- `AICRM_PHASE5C_WECOM_TAG_PRODUCTION_DRY_RUN_APPROVED=1`
- `AICRM_WECOM_TAG_CONFIG_REVIEWED=1`
- `--dry-run`
- `--confirm-no-live-call`

This runner never calls WeCom, never writes a tag, and never sends a message. It emits blocked or ready evidence only.

## Idempotency Policy

Live mark/unmark methods require an idempotency key. Same key plus same payload returns replay evidence. Same key plus different payload returns `duplicate_idempotency_key`. Blocked requests have no partial external side effect.

## Error Mapping

Required error codes:

- `live_adapter_not_enabled`
- `live_call_not_approved`
- `wecom_config_missing`
- `idempotency_key_required`
- `duplicate_idempotency_key`
- `invalid_tag_id`
- `external_userid_missing`
- `wecom_live_call_failed`
- `forbidden_in_production_without_approval`

## Business Continuity

Existing production behavior remains unchanged. Legacy fallback remains retained. The new code only creates a guarded Next-side adapter and integration gateway boundary for later approved staging evidence.

## Phase 5D Recommendation

- next: phase_5d_wecom_tag_staging_live_canary_evidence_bundle
- route_family: /api/admin/wecom/tags*
- controlled staging live canary evidence
- cleanup/rollback package
- no production live canary unless separately approved

This PR must not implement Phase 5D.
