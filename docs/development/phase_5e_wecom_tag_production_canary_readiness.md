# Phase 5E WeCom Tag Production Canary Readiness

## Status

- status: phase_5e_wecom_tag_production_canary_readiness_no_execution
- bundle_type: phase_5_external_adapter_production_canary_readiness_bundle
- route_family: /api/admin/wecom/tags*
- capability_owner: aicrm_next.customer_tags
- production canary readiness only
- no production live WeCom call
- no production tag write
- no production owner switch
- no fallback removal
- no production_compat change
- no outbound send
- no canary execution
- delete_ready false

## Staging Evidence Requirement

Phase 5E requires Phase 5D staging evidence before production canary planning can be considered ready. Blocked staging evidence does not qualify. Accepted evidence must be redacted, must not include raw secrets or tokens, and must show side_effect_safety.

The readiness runner checks:

- staging evidence JSON exists and parses
- evidence result_status is not blocked
- evidence is staging-only
- evidence records `production_live_call_executed=false`
- evidence includes side_effect_safety
- evidence contains redacted target evidence
- evidence does not include raw secret/token fields

## Production Canary Readiness Gates

All gates are required before Phase 5F can be planned:

- `AICRM_PHASE5E_WECOM_TAG_PRODUCTION_CANARY_PLANNING_APPROVED=1`
- `AICRM_PHASE5E_WECOM_TAG_PRODUCTION_CONFIG_REVIEWED=1`
- `AICRM_PHASE5E_WECOM_TAG_ROLLBACK_OWNER_APPROVED=1`
- `AICRM_PHASE5E_WECOM_TAG_TARGET_POLICY_REVIEWED=1`
- accepted Phase 5D staging evidence
- `--confirm-no-production-live-call`
- `--confirm-no-production-tag-write`

If any gate is missing, the runner emits blocked readiness evidence and never calls WeCom.

## Production Target Safety Policy

- Single target only for the first production canary.
- Explicit external_userid is required later in Phase 5F.
- Explicit tag_id is required later in Phase 5F.
- No batch target.
- No customer pool target.
- No automatic segment target.
- No outbound send.
- No timer or automation execution.
- external_userid must be redacted in evidence.
- Raw token and raw secret values must never be printed.

## Rollback / Cleanup Package

- Rollback owner is required.
- Cleanup must be explicit.
- Cleanup can only unmark the same tag from the same approved target.
- Cleanup evidence must be captured.
- No automatic cleanup without approval.
- No production batch cleanup.

## Phase 5F Recommendation

- next: phase_5f_wecom_tag_production_live_canary_execution_bundle
- route_family: /api/admin/wecom/tags*
- controlled production live canary execution evidence bundle
- single target
- single tag
- explicit confirm flags
- no route owner switch
- no fallback removal
- no production_compat change
