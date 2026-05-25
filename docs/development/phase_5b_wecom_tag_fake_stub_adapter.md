# Phase 5B WeCom Tag Fake/Stub Adapter

## Status

- status: phase_5b_wecom_tag_fake_stub_adapter
- bundle type: phase_5_external_adapter_fake_stub_runtime_and_readiness_bundle
- route family: /api/admin/wecom/tags*
- capability owner: aicrm_next.customer_tags
- fake/stub runtime implemented
- no live WeCom call
- no production tag write
- no production owner switch
- no fallback removal
- no production_compat change
- no canary approval
- delete_ready false

## Implemented Fake/Stub Methods

- `list_wecom_tags`
- `validate_tag_ids`
- `dry_run_mark_tags`
- `dry_run_unmark_tags`

The adapter returns deterministic fake tag data and dry-run evidence only. It records idempotency state in local memory for replay/conflict proof and does not persist external_userid or tag writes.

## Readiness Packages

- staging fake/stub smoke package: `tools/run_phase5b_wecom_tag_fake_stub_staging_smoke.py`
- production fake/stub dry-run package: `tools/run_phase5b_wecom_tag_fake_stub_production_dry_run.py`

The staging runner is blocked by default unless `AICRM_PHASE5B_WECOM_TAG_STAGING_SMOKE_APPROVED=1`.

The production dry-run runner is blocked by default unless `AICRM_PHASE5B_WECOM_TAG_PRODUCTION_DRY_RUN_APPROVED=1`, `AICRM_PHASE5B_WECOM_TAG_PRODUCTION_CONFIG_REVIEWED=1`, `--dry-run`, and `--confirm-no-live-call` are all present.

## Boundaries

- no externalcontact/mark_tag live call
- no externalcontact/get_corp_tag_list live call
- no token usage
- no CorpID requirement
- no outbound send
- no customer sync
- no production route owner switch
- no production_compat change
- no fallback removal

## Idempotency Policy

Write-like dry-runs require an idempotency key. Same key plus same payload returns replay. Same key plus different payload returns conflict with `duplicate_idempotency_key`.

## Evidence Policy

Every adapter response includes `live_call_executed=false`, `mark_tag_executed=false`, `unmark_tag_executed=false`, `outbound_send_executed=false`, `token_used=false`, `network_call_executed=false`, and `production_behavior_changed=false`.

## Production Behavior

Production behavior is unchanged. In `AICRM_NEXT_ENV=production`, the fake/stub adapter may return contract and dry-run evidence only. It does not claim real external tag-write completion and does not treat fixture/local_contract data as production external success.

## Fallback Behavior

Legacy fallback remains retained. This bundle does not narrow or remove `production_compat`.

## Business Continuity

Current admin WeCom tag management remains available through the existing production path while Next gains a testable fake/stub adapter boundary for future gated integration.

## Phase 5C Recommendation

- next: phase_5c_wecom_tag_live_adapter_behind_flag_bundle
- route_family: /api/admin/wecom/tags*
- live WeCom adapter implementation behind explicit flag
- no live call by default
- owner approval required
- staging/live canary separate

This PR must not implement Phase 5C.
