# D7.6 Archive / Contacts / Identity Adapter Contract

## Scope

D7.6 defines fake/staging-disabled adapter boundaries for Archive sync, Contacts sync, Identity mapping, and Customer Read Model projection updates. This slice does not call WeCom, does not fetch real conversation archive, does not sync real contacts, does not write production identity mappings, and does not write production customer projections.

## Adapter Result Shape

Every D7.6 adapter method returns:

- `ok`
- `adapter`
- `mode`
- `operation`
- `idempotency_key`
- `target`
- `result`
- `audit_id`
- `side_effect_executed`
- `error_code`
- `error_message`

`target` may include `external_userid`, `openid`, `unionid`, `person_id`, `corp_id`, `follow_user_userid`, `msgid`, `sync_cursor`, and `projection_name`. Secret-like fields including access tokens, private keys, archive keys, certificates, and credentials are scrubbed.

## ArchiveSyncAdapter

Methods:

- `fetch_recent_messages`
- `fetch_incremental_archive_messages`
- `normalize_archive_message`
- `build_archive_sync_preview`
- `record_archive_sync_audit`

The adapter returns deterministic fake archive previews and audit records. It never calls the WeCom archive SDK in D7.6.

## ContactsSyncAdapter

Methods:

- `fetch_external_contacts`
- `fetch_contact_detail`
- `fetch_follow_user_relations`
- `build_contacts_sync_preview`
- `record_contacts_sync_audit`

The adapter returns deterministic fake contacts sync results and audit records. It never calls the WeCom contacts API in D7.6.

## IdentityMappingAdapter

Methods:

- `resolve_person_identity`
- `upsert_identity_mapping`
- `link_openid_unionid_external_userid`
- `build_identity_mapping_preview`
- `record_identity_mapping_audit`

The adapter records fake identity resolution and write intents. It does not write production identity mappings.

## CustomerProjectionSyncGateway

Methods:

- `update_customer_list_projection`
- `update_customer_detail_projection`
- `update_customer_timeline_projection`
- `update_recent_messages_projection`
- `build_projection_sync_preview`
- `record_projection_sync_audit`

The gateway records fake projection update intents only. It does not write production Customer Read Model tables.

## Modes

| mode | behavior |
| --- | --- |
| `fake` | deterministic fake result, audit event, idempotency, no side effect |
| `disabled` | stable disabled error with audit event |
| `staging` | staging-shaped fake result, audit event, no side effect |
| `production` | requires explicit env guard; real behavior is not implemented in D7.6 and fails closed |

Default modes:

- `AICRM_NEXT_ARCHIVE_SYNC_MODE=fake`
- `AICRM_NEXT_CONTACTS_SYNC_MODE=fake`
- `AICRM_NEXT_IDENTITY_MAPPING_MODE=fake`
- `AICRM_NEXT_CUSTOMER_PROJECTION_SYNC_MODE=fake`

Production guards:

- `AICRM_NEXT_ENABLE_REAL_ARCHIVE_SYNC=true`
- `AICRM_NEXT_ENABLE_REAL_CONTACTS_SYNC=true`
- `AICRM_NEXT_ENABLE_REAL_IDENTITY_MAPPING=true`
- `AICRM_NEXT_ENABLE_REAL_CUSTOMER_PROJECTION_SYNC=true`

Without the explicit guard, production mode returns `production_guard_failed`. With the explicit guard, this D7.6 slice still returns `production_not_implemented`.

## Idempotency

Idempotency keys use `operation + canonical target/payload`. Repeated fake operations with the same key return the same deterministic fake result. This is required for archive cursor replay, message dedupe, contact page replay, identity mapping replay, and projection refresh replay.

## Audit

All modes write an in-memory audit event with:

- `audit_id`
- `adapter`
- `operation`
- `mode`
- `idempotency_key`
- `side_effect_executed`
- `status`
- `error_code`
- `created_at`

D7.6 does not connect audit events to a production database.

## Side-Effect Safety

The following flags remain false in fake, disabled, staging, and guarded production behavior:

- `real_archive_sync_executed`
- `real_contacts_sync_executed`
- `real_identity_mapping_write_executed`
- `real_customer_projection_write_executed`
- `real_wecom_call_executed`

## API Compatibility

Existing Customer Read Model readonly endpoints, Identity resolve API shape, and MCP customer context shape remain compatible. D7.6 only adds `adapter_contract` and `side_effect_safety` metadata to Next fixture responses where applicable.

## Risk Notes

- Duplicate external_userid mapping: future real writes need unique constraints and conflict policy.
- Openid / unionid mismatch: future resolver must keep mismatch warnings and operator review.
- Archive cursor replay: future sync must dedupe by cursor, msgid, and corp.
- Message idempotency: future message projection must not duplicate timeline or recent-message rows.
- Timeline projection consistency: future projection writes need transactional grouping.
- MCP customer context staleness: future context responses should expose sync lag.
- Rollback: disable adapter modes first and keep legacy archive, contacts, and identity fallback retained.

## Next Steps

Run D7.6 checker, Customer smoke, Customer parity, and D7.6 tests. Real WeCom archive sync, contacts sync, identity writes, and production projection writes remain future work after separate approval.
