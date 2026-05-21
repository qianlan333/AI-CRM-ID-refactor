# D7.3 User Ops DND / Batch Send / WeCom Dispatch Adapter Contract

## Scope

D7.3 establishes formal adapter and gateway boundaries for User Ops DND writes, batch-send preview and execute, WeCom message dispatch, and deferred jobs.

This slice does not call WeCom, send private messages, send group messages, post moments, upload WeCom media, run deferred jobs, read production credentials, change production config, or switch production traffic.

## Adapters Implemented

| adapter | file | responsibility |
| --- | --- | --- |
| `UserOpsDndWriteGateway` | `aicrm_next/integration_gateway/user_ops_adapters.py` | DND enable/cancel/preview/audit boundary |
| `UserOpsBatchSendGateway` | `aicrm_next/integration_gateway/user_ops_adapters.py` | batch-send preview/execute/send-record/summary boundary |
| `WeComMessageDispatchAdapter` | `aicrm_next/integration_gateway/user_ops_adapters.py` | private message, group message, moment, dispatch preview/target/audit boundary |
| `UserOpsDeferredJobGateway` | `aicrm_next/integration_gateway/user_ops_adapters.py` | enqueue/run/preview/audit boundary for deferred jobs |

## Stable Result Shape

Every method returns:

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

The `target` may include `external_userid`, `owner_userid`, `mobile`, `record_id`, `batch_id`, `job_id`, `send_channel`, and `media_refs`. Secret-like keys are scrubbed before they enter the returned target.

## DND Write Gateway

`UserOpsDndWriteGateway` supports:

- `enable_do_not_disturb`
- `cancel_do_not_disturb`
- `build_dnd_preview`
- `record_dnd_audit`

Fake and staging modes record an audit event and return deterministic operation ids. They do not write to any external system. The User Ops application still updates the local Next fixture/repository state for API parity after the gateway boundary accepts the write intent.

## Batch-Send Gateway

`UserOpsBatchSendGateway` supports:

- `build_batch_send_preview`
- `execute_batch_send`
- `create_send_record`
- `build_send_result_summary`

Preview and execute now pass through this gateway before application code builds parity-compatible responses. Fake execution returns `dispatched=false`.

## WeCom Dispatch Adapter

`WeComMessageDispatchAdapter` supports:

- `send_private_message`
- `send_group_message`
- `send_moment`
- `build_dispatch_preview`
- `resolve_dispatch_target`
- `record_dispatch_audit`

All D7.3 dispatch paths return fake task ids and `sent=false`. The compatibility `DispatchGateway` delegates to this adapter instead of the older standalone fake dispatch object.

## Deferred Job Gateway

`UserOpsDeferredJobGateway` supports:

- `enqueue_deferred_job`
- `run_due_jobs`
- `build_deferred_job_preview`
- `record_deferred_job_audit`

D7.3 provides a fake run boundary only. `run_due_jobs` returns `executed=false` and `executed_count=0`.

## Mode Behavior

| mode | behavior |
| --- | --- |
| `fake` | deterministic fake result, audit recorded, no outbound call |
| `disabled` | deterministic blocked error, audit recorded, no outbound call |
| `staging` | staging-shaped fake result, audit recorded, no outbound call |
| `production` | fails closed without explicit env flag; with flag, returns not implemented in this slice |

## Env Flags

Default mode flags:

- `AICRM_NEXT_USER_OPS_DND_MODE=fake`
- `AICRM_NEXT_USER_OPS_BATCH_SEND_MODE=fake`
- `AICRM_NEXT_WECOM_DISPATCH_MODE=fake`
- `AICRM_NEXT_USER_OPS_DEFERRED_JOBS_MODE=fake`

Real-call enable flags required by future slices:

- `AICRM_NEXT_ENABLE_REAL_USER_OPS_DND=true`
- `AICRM_NEXT_ENABLE_REAL_USER_OPS_BATCH_SEND=true`
- `AICRM_NEXT_ENABLE_REAL_WECOM_DISPATCH=true`
- `AICRM_NEXT_ENABLE_REAL_USER_OPS_DEFERRED_JOBS=true`

D7.3 does not implement real outbound behavior even when these flags are set.

## Idempotency

All gateways use `aicrm_next/integration_gateway/idempotency.py`.

Keys are generated from operation name plus canonical target payload, including target identity, batch metadata, content hash, media reference summaries, or job metadata. Repeated fake calls with the same key return the same deterministic `result`.

## Audit

All gateways use `aicrm_next/integration_gateway/audit.py`.

Audit records include:

- `audit_id`
- `adapter`
- `operation`
- `mode`
- `idempotency_key`
- `side_effect_executed`
- `status`
- `error_code`
- `created_at`

The D7.3 sink is in-memory only.

## Side-Effect Safety

D7.3 safety flags remain false:

- `real_dnd_write_executed=false`
- `real_batch_send_executed=false`
- `real_wecom_dispatch_executed=false`
- `real_deferred_jobs_executed=false`
- `real_wecom_media_upload_executed=false`
- `side_effect_executed=false`

## API Compatibility

Existing User Ops readonly APIs are unchanged.

DND, batch-send preview, batch-send execute, and send-record response shapes preserve the existing parity fields. Additional `side_effect_safety` and `adapter_contract` metadata is appended for auditability and does not replace existing response keys.

## Not Implemented

D7.3 intentionally does not implement:

- real WeCom private message send
- real WeCom group message send
- real WeCom moment send
- real WeCom media upload
- real deferred job execution
- production credential loading
- production traffic switching

## Rollback

Rollback is flag-first:

1. Set D7.3 modes to `disabled`.
2. Keep legacy User Ops write/external fallback files retained.
3. Revert the D7.3 adapter application wiring if needed.

## Next Steps

- Run D7.3 checker and targeted tests.
- Design staging allowlist and operator approval semantics for a later dispatch slice.
- Keep legacy User Ops write/external fallback until real-call evidence, rollback proof, and human approval exist.
