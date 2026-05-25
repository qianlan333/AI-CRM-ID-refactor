# Phase 5A WeCom Tag Adapter Contract

## Status

- status: phase_5a_wecom_tag_adapter_contract
- bundle type: phase_5_external_adapter_contract_bundle
- route family: /api/admin/wecom/tags*
- capability owner: aicrm_next.customer_tags
- integration boundary: aicrm_next.integration_gateway
- no live WeCom call
- no production tag write
- no outbound send
- no production owner switch
- no fallback removal
- no production_compat change
- no OAuth callback cutover
- no timer / automation execution
- no canary approval
- delete_ready false

## Contract Scope

This bundle covers only the WeCom tag adapter contract for `/api/admin/wecom/tags*`.

Included contract surfaces:

- list tags contract
- tag lookup / normalize contract
- future mark_tag / unmark_tag contract shape
- fake/stub adapter response
- dry-run request validation
- error mapping
- retry / idempotency policy
- audit/evidence shape

Excluded live behavior:

- externalcontact/mark_tag live call
- externalcontact/get_corp_tag_list live call
- message send
- customer sync
- OAuth callback
- payment behavior
- media upload
- OpenClaw/MCP live call

The existing legacy WeCom tag routes and services are contract references only. This bundle does not add new legacy business logic and does not move production route ownership.

## Adapter Contract

All adapter methods return contract evidence only in Phase 5A. Every method must include `adapter_mode`, `live_call_executed=false`, and `side_effect_safety` in its response.

### list_wecom_tags()

- input fields: none for the default contract; future filters may include `group_id`, `tag_id`, and `include_disabled`.
- output fields: `adapter_mode`, `live_call_executed`, `tags`, `groups`, `normalized_tag_ids`, `result_status`, `side_effect_safety`, `timestamp`.
- validation: filter values are trimmed strings; empty filters are ignored.
- error codes: `wecom_config_missing`, `adapter_unavailable`, `live_call_not_enabled`, `forbidden_in_production_without_approval`.
- idempotency behavior: read-only contract method; idempotency key is not required.
- side_effect_safety: no network call, no token usage, no CorpID usage, no DB mutation, no production owner switch.
- live_call_executed: false.

### validate_tag_ids(tag_ids)

- input fields: `tag_ids` as a non-empty list of strings.
- output fields: `adapter_mode`, `live_call_executed`, `requested_tag_ids`, `normalized_tag_ids`, `invalid_tag_ids`, `result_status`, `error_code`, `side_effect_safety`, `timestamp`.
- validation: trims whitespace, removes empty values, deduplicates while preserving first occurrence, and verifies IDs against the deterministic fake tag list.
- error codes: `invalid_tag_id`, `adapter_unavailable`, `live_call_not_enabled`, `forbidden_in_production_without_approval`.
- idempotency behavior: validation-only contract method; idempotency key is not required.
- side_effect_safety: no external write, no network call, no token usage, no external_userid write.
- live_call_executed: false.

### dry_run_mark_tags(external_userid, tag_ids, operator, idempotency_key)

- input fields: `external_userid`, `tag_ids`, `operator`, `idempotency_key`.
- output fields: `adapter_mode`, `live_call_executed`, `mark_tag_executed=false`, `external_userid_redacted`, `requested_tag_ids`, `normalized_tag_ids`, `operator`, `idempotency_key`, `request_hash`, `result_status`, `error_code`, `side_effect_safety`, `timestamp`.
- validation: `external_userid`, `operator`, and `idempotency_key` are required; tag IDs must pass `validate_tag_ids`.
- error codes: `external_userid_missing`, `idempotency_key_required`, `duplicate_idempotency_key`, `invalid_tag_id`, `live_call_not_enabled`, `adapter_unavailable`, `forbidden_in_production_without_approval`.
- idempotency behavior: same key plus same payload returns replay; same key plus different payload returns conflict.
- side_effect_safety: no externalcontact/mark_tag call, no production tag write, no DB mutation, no outbound send.
- live_call_executed: false.

### dry_run_unmark_tags(external_userid, tag_ids, operator, idempotency_key)

- input fields: `external_userid`, `tag_ids`, `operator`, `idempotency_key`.
- output fields: `adapter_mode`, `live_call_executed`, `unmark_tag_executed=false`, `external_userid_redacted`, `requested_tag_ids`, `normalized_tag_ids`, `operator`, `idempotency_key`, `request_hash`, `result_status`, `error_code`, `side_effect_safety`, `timestamp`.
- validation: `external_userid`, `operator`, and `idempotency_key` are required; tag IDs must pass `validate_tag_ids`.
- error codes: `external_userid_missing`, `idempotency_key_required`, `duplicate_idempotency_key`, `invalid_tag_id`, `live_call_not_enabled`, `adapter_unavailable`, `forbidden_in_production_without_approval`.
- idempotency behavior: same key plus same payload returns replay; same key plus different payload returns conflict.
- side_effect_safety: no externalcontact/mark_tag call, no production tag write, no DB mutation, no outbound send.
- live_call_executed: false.

## Fake/Stub Behavior

Phase 5A fake/stub mode is deterministic and local:

- deterministic fake tag list
- no live network call
- no WeCom secrets required
- no token usage
- no CorpID usage required
- no external_userid write
- returns contract evidence only
- production-ready outcome claims are not allowed

The deterministic fake tags are stable contract fixtures, not production data. They may be used for schema, validation, idempotency, and evidence tests only.

## Error Mapping

Required error codes:

- `wecom_config_missing`: future live configuration is absent; Phase 5A does not read the secret.
- `invalid_tag_id`: one or more requested tag IDs are empty, unknown, or malformed for the fake/stub contract.
- `external_userid_missing`: write-like dry-run request omitted `external_userid`.
- `idempotency_key_required`: write-like dry-run request omitted `idempotency_key`.
- `duplicate_idempotency_key`: same idempotency key was reused with a different request hash.
- `live_call_not_enabled`: live WeCom calls are disabled for Phase 5A.
- `adapter_unavailable`: adapter cannot produce contract evidence.
- `forbidden_in_production_without_approval`: production write or live call attempted without owner approval.

## Idempotency / Retry Policy

- idempotency key is required for future write-like dry-runs.
- same key plus same payload returns replay.
- same key plus different payload returns conflict.
- retry is safe because Phase 5A has no external side effect.
- there can be no partial external side effect because live calls are disabled.
- request hash must be generated from a canonical method and payload shape.

## Evidence / Audit Policy

Evidence records must include:

- `adapter_mode`
- `live_call_executed=false`
- `requested_tag_ids`
- `normalized_tag_ids`
- `external_userid` redaction policy: store only a prefix/suffix redaction or `<redacted>`; never emit the full value.
- `operator`
- `idempotency_key`
- `request_hash`
- `result_status`
- `side_effect_safety`
- `timestamp`

## Production Behavior

Production behavior is unchanged. Current legacy fallback remains retained. This bundle does not switch route owner, alter production_compat, enable live WeCom calls, or claim production tag-write success.

## Business Continuity

The contract prepares a safe adapter boundary for customer tags while preserving the current admin WeCom tag management path. Operators keep the existing production behavior, and Phase 5A evidence gives engineering a testable path for the later fake/stub adapter bundle.

## Phase 5B Recommendation

Recommended next bundle:

- next: phase_5b_wecom_tag_fake_stub_adapter_bundle
- route_family: /api/admin/wecom/tags*
- no live WeCom call
- no production tag write
- no production owner switch

This PR must not implement Phase 5B.
