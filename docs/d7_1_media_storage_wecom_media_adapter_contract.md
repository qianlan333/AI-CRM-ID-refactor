# D7.1 Media Storage / WeCom Media Adapter Contract

## Scope

D7.1 establishes the Media Library external adapter boundary for cloud storage and WeCom media. This is the first D7 write/external replacement implementation slice. It does not enable real cloud upload, real WeCom media upload, production route changes, or production traffic cutover.

## Implemented Adapters

| adapter | owning_context | methods | default_mode | real_external_call_status |
| --- | --- | --- | --- | --- |
| CloudStorageAdapter | `aicrm_next.integration_gateway` | `put_object`, `put_base64_object`, `put_remote_reference`, `get_public_reference`, `delete_object` | `fake` | not implemented and not executed |
| WeComMediaAdapter | `aicrm_next.integration_gateway` | `upload_image`, `upload_attachment`, `resolve_media_id`, `delete_or_expire_reference` | `fake` | not implemented and not executed |

## Stable Result Shape

Every adapter method returns the same shape:

| field | meaning |
| --- | --- |
| `ok` | success flag for the adapter call |
| `adapter` | adapter name |
| `mode` | `fake`, `disabled`, `staging`, or `production` |
| `operation` | method operation name |
| `idempotency_key` | deterministic guard key |
| `storage_key` | fake/staging cloud object key when applicable |
| `media_id` | fake/staging WeCom media id when applicable |
| `public_url` | fake/staging public reference when applicable |
| `reference_url` | fake/staging reference URL |
| `audit_id` | in-memory audit event id |
| `side_effect_executed` | always `false` in D7.1 |
| `error_code` | stable machine-readable error |
| `error_message` | stable human-readable error |

## Mode Behavior

| mode | CloudStorageAdapter behavior | WeComMediaAdapter behavior | side_effect_executed |
| --- | --- | --- | --- |
| fake | returns deterministic fake object references | returns deterministic fake media ids | false |
| disabled | returns `adapter_disabled` error | returns `adapter_disabled` error | false |
| staging | returns staging-shaped fake references only | returns staging-shaped fake media ids only | false |
| production | fails closed unless explicit env flag is present; real upload still not implemented | fails closed unless explicit env flag is present; real upload still not implemented | false |

## Env Flags

| flag | default | purpose |
| --- | --- | --- |
| `AICRM_NEXT_MEDIA_STORAGE_MODE` | `fake` | cloud adapter mode |
| `AICRM_NEXT_WECOM_MEDIA_MODE` | `fake` | WeCom media adapter mode |
| `AICRM_NEXT_ENABLE_REAL_CLOUD_STORAGE` | unset / false | required before any future cloud real-call implementation can run |
| `AICRM_NEXT_ENABLE_REAL_WECOM_MEDIA` | unset / false | required before any future WeCom media real-call implementation can run |

Production mode without the explicit enable flag returns `production_guard_failed`. Production mode with the explicit flag still returns `production_not_implemented` in D7.1.

## Idempotency

The adapter boundary derives idempotency keys from operation name and canonical payload details such as content hash, source reference, file name, and content type. Repeated fake calls with the same idempotency key return the same `storage_key` or `media_id`.

## Audit

D7.1 uses an in-memory audit sink for contract validation. Each adapter call records:

| field | present |
| --- | --- |
| `audit_id` | yes |
| `adapter` | yes |
| `operation` | yes |
| `mode` | yes |
| `idempotency_key` | yes |
| `side_effect_executed` | yes |
| `status` | yes |
| `error_code` | yes |
| `created_at` | yes |

This is not a production audit database.

## Media Library API Compatibility

Media Library still preserves existing response shapes for list/detail and fake write routes. `from-url`, `from-base64`, and upload-like image/attachment writes now pass through the integration gateway adapter boundary before storing fake media records. `from-url` stores the original source URL as a remote reference and never fetches it.

## Side-Effect Safety

| side_effect | D7.1 status |
| --- | --- |
| real cloud upload | false |
| real WeCom media upload | false |
| remote URL fetch | false |
| production credential read | false |
| production traffic cutover | false |

## Rollback

Rollback is code-only: revert the D7.1 PR to restore the previous direct fake import behavior. No production flags, external credentials, storage buckets, WeCom media state, or Nginx/deploy settings are changed by this slice.

## Next Steps

After D7.1 acceptance, the next implementation can add staging-only adapter fixtures and stronger file size/type policy tests. Real production external calls remain blocked pending explicit implementation, evidence, and human approval.
