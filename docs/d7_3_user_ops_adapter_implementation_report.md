# D7.3 User Ops Adapter Implementation Report

## Summary

D7.3 adds guarded fake adapter contracts for User Ops DND, batch-send, WeCom dispatch, and deferred jobs. The implementation reuses the D7.1/D7.2 in-memory audit and idempotency helpers and keeps all real side effects off.

## Files

Implemented:

- `aicrm_next/integration_gateway/user_ops_adapters.py`
- `aicrm_next/integration_gateway/user_ops_contracts.py`
- `aicrm_next/ops_enrollment/application.py`
- `aicrm_next/integration_gateway/dispatch.py`
- `tools/check_d7_3_user_ops_adapter_contract.py`
- `tests/test_d7_3_user_ops_adapter_contract.py`

## Application Wiring

| User Ops path | D7.3 boundary |
| --- | --- |
| DND enable/cancel | `UserOpsDndWriteGateway` before local fixture/repo state update |
| batch-send preview | `UserOpsBatchSendGateway.build_batch_send_preview` |
| batch-send execute | `UserOpsBatchSendGateway.execute_batch_send` |
| send records | `UserOpsBatchSendGateway.create_send_record` and `build_send_result_summary` |
| WeCom fake dispatch | `WeComMessageDispatchAdapter.send_private_message` |
| deferred job fake run | `UserOpsDeferredJobGateway.run_due_jobs` |

## Mode Guard

The default modes are fake:

- `AICRM_NEXT_USER_OPS_DND_MODE`
- `AICRM_NEXT_USER_OPS_BATCH_SEND_MODE`
- `AICRM_NEXT_WECOM_DISPATCH_MODE`
- `AICRM_NEXT_USER_OPS_DEFERRED_JOBS_MODE`

Production mode requires these explicit future flags:

- `AICRM_NEXT_ENABLE_REAL_USER_OPS_DND`
- `AICRM_NEXT_ENABLE_REAL_USER_OPS_BATCH_SEND`
- `AICRM_NEXT_ENABLE_REAL_WECOM_DISPATCH`
- `AICRM_NEXT_ENABLE_REAL_USER_OPS_DEFERRED_JOBS`

Without the flag, production mode fails closed. With the flag, D7.3 still returns `production_not_implemented`.

## Idempotency and Audit

Idempotency uses `operation + canonical target payload` through `make_idempotency_key`. Audit uses the shared in-memory sink and records adapter name, operation, mode, key, status, error code, timestamp, and the false side-effect flag.

## Side-Effect Safety

All D7.3 paths report:

- real DND write: false
- real batch-send execute: false
- real WeCom dispatch: false
- real deferred job execution: false
- real WeCom media upload: false

## API Compatibility

The existing User Ops parity fields remain in place for readonly APIs, DND, batch-send preview/execute, and send-records. D7.3 adds adapter metadata without removing existing keys.

## Real Calls

Not implemented in this slice:

- WeCom private message send
- WeCom group message send
- WeCom moment send
- deferred job execution
- production credentials
- production traffic change

## Rollback

Use mode flags to disable the new boundaries, or revert the D7.3 adapter wiring. Legacy User Ops write/external fallback remains retained.

## Next Steps

- Run `tools/check_d7_3_user_ops_adapter_contract.py`.
- Keep User Ops external fallback retained.
- In a later slice, design staging allowlists, operator approval, queue leases, and real dispatch proof.
