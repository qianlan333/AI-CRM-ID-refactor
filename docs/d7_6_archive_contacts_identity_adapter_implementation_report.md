# D7.6 Archive / Contacts / Identity Adapter Implementation Report

## Summary

D7.6 adds formal fake/staging-disabled adapter boundaries for Archive sync, Contacts sync, Identity mapping, and Customer Read Model projection updates. The implementation preserves existing Customer Read Model and Identity fixture behavior while recording deterministic adapter results through the integration gateway.

## Implemented Files

- `aicrm_next/integration_gateway/customer_sync_contracts.py`
- `aicrm_next/integration_gateway/customer_sync_adapters.py`
- `aicrm_next/customer_read_model/application.py`
- `aicrm_next/identity_contact/application.py`
- `tools/customer_read_model_gray_smoke.py`
- `tools/compare_customer_read_model_parity.py`
- `tools/check_d7_6_customer_sync_adapter_contract.py`
- `tests/test_d7_6_customer_sync_adapter_contract.py`
- `tests/fixtures/old_customer_read_model/*.json`

## Adapter Coverage

| adapter | status | notes |
| --- | --- | --- |
| ArchiveSyncAdapter | fake_contract_ready | recent messages, incremental archive, message normalization, preview, audit |
| ContactsSyncAdapter | fake_contract_ready | contacts list, contact detail, follow-user relation, preview, audit |
| IdentityMappingAdapter | fake_contract_ready | resolve, upsert intent, openid/unionid/external_userid link intent, preview, audit |
| CustomerProjectionSyncGateway | fake_contract_ready | list/detail/timeline/recent-message projection update intents, preview, audit |

## Mode Guards

Defaults are fake. Disabled mode returns `adapter_disabled`. Production mode without explicit enable flags returns `production_guard_failed`. Production mode with explicit flags still returns `production_not_implemented` in this slice.

## Idempotency And Audit

D7.6 reuses `aicrm_next/integration_gateway/idempotency.py` and `aicrm_next/integration_gateway/audit.py`. Repeated fake calls with the same idempotency key return the same fake result. Every adapter call creates an audit event, including disabled and guarded production calls.

## Customer / Identity Wiring

- Customer list path records `ContactsSyncAdapter.fetch_external_contacts` and `CustomerProjectionSyncGateway.update_customer_list_projection`.
- Customer detail path records `ContactsSyncAdapter.fetch_contact_detail` and `CustomerProjectionSyncGateway.update_customer_detail_projection`.
- Customer timeline path records `CustomerProjectionSyncGateway.update_customer_timeline_projection`.
- Recent messages path records `ArchiveSyncAdapter.fetch_recent_messages` and `CustomerProjectionSyncGateway.update_recent_messages_projection`.
- Customer chat context carries additive adapter metadata from detail, timeline, and recent-message queries.
- Identity resolve path records `IdentityMappingAdapter.resolve_person_identity`.
- Identity upsert/link command wrappers use `IdentityMappingAdapter`.

Existing API outputs remain compatible. New fields are additive: `adapter_contract` and `side_effect_safety`.

## Side-Effect Safety

D7.6 did not execute:

- real archive sync
- real contacts sync
- real identity mapping write
- real customer projection write
- real WeCom call

No production, deploy, nginx, systemd, or traffic configuration was changed.

## Compatibility Evidence

Expected verification:

- `tools/check_d7_6_customer_sync_adapter_contract.py`
- `tools/customer_read_model_gray_smoke.py`
- `tools/compare_customer_read_model_parity.py`
- `tests/test_d7_6_customer_sync_adapter_contract.py`

Customer parity remains fixture/TestClient based and uses readonly endpoints only.

## Not Implemented In D7.6

- real WeCom archive SDK calls
- real WeCom contacts API calls
- production identity mapping writes
- production Customer Read Model projection writes
- production credential loading
- production traffic cutover

## Risk Notes

- Duplicate external_userid mapping requires future unique constraints and merge policy.
- Openid / unionid mismatch requires future conflict review.
- Archive cursor replay requires persistent cursor locks and msgid dedupe.
- Message idempotency requires projection-level replay guards.
- Timeline projection consistency requires transactional writes.
- MCP customer context staleness needs sync-lag reporting before real sync.

## Rollback

Set adapter modes to `disabled` or revert D7.6 wiring. Legacy archive, contacts, and identity fallback remains retained for real sync and write behavior.

## Next Step

Proceed to D7.6 validation review after checker, tests, Customer smoke, and Customer parity pass.
