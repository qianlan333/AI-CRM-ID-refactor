# D7.4 Product Payment Adapter Implementation Report

## Scope

D7.4 implements Product/Commerce adapter contracts for Product writes, WeChat Pay, Alipay, payment notify, and Alipay return. The implementation is fake or disabled by default and uses shared in-memory idempotency and audit helpers.

No production payment provider call, checkout execution, notify processing, credential read, production config edit, or traffic switch was performed.

Status: `scope_isolated`. D7.1 Media, D7.2 Questionnaire, and D7.3 User Ops are accepted prerequisites in the current dirty worktree; D7.4 is only the Product/Payment increment on top of that baseline.

## Implemented Contracts

| contract | implementation | status |
| --- | --- | --- |
| ProductWriteGateway | `aicrm_next/integration_gateway/payment_adapters.py` | fake_contract_ready |
| WeChatPayAdapter | `aicrm_next/integration_gateway/payment_adapters.py` | fake_contract_ready |
| AlipayAdapter | `aicrm_next/integration_gateway/payment_adapters.py` | fake_contract_ready |
| PaymentNotifyGateway | `aicrm_next/integration_gateway/payment_adapters.py` | fake_contract_ready |
| PaymentReturnGateway | `aicrm_next/integration_gateway/payment_adapters.py` | fake_contract_ready |

## Mode Behavior

| mode | behavior |
| --- | --- |
| fake | deterministic fake result, audit event, no external call |
| disabled | stable `adapter_disabled` error, audit event |
| staging | staging-shaped fake result, audit event, no external call |
| production | explicit env flag required; D7.4 still returns `production_not_implemented` when enabled |

Production guard flags:

- `AICRM_NEXT_ENABLE_REAL_PRODUCT_WRITES`
- `AICRM_NEXT_ENABLE_REAL_WECHAT_PAY`
- `AICRM_NEXT_ENABLE_REAL_ALIPAY`
- `AICRM_NEXT_ENABLE_REAL_PAYMENT_NOTIFY`

## Commerce Application Integration

`aicrm_next.commerce.application` now routes:

- product create/update/enable/disable/delete through `ProductWriteGateway`
- WeChat fake checkout through `WeChatPayAdapter`
- Alipay fake checkout through `AlipayAdapter`
- notify through `PaymentNotifyGateway`
- Alipay return through `PaymentReturnGateway`

Existing payload compatibility is preserved and adapter metadata is additive.

## Idempotency And Audit

Shared helpers:

- `aicrm_next/integration_gateway/idempotency.py`
- `aicrm_next/integration_gateway/audit.py`

Repeated fake checkout with the same key returns the same fake transaction/prepay result. Repeated fake notify with the same key returns the same fake notify result. All modes create audit records with `side_effect_executed=false`.

## Side Effect Safety

D7.4 keeps the following false:

- `real_product_write_executed`
- `real_wechat_pay_executed`
- `real_alipay_executed`
- `real_payment_notify_executed`
- `real_payment_provider_called`

## Payment-Specific Risks

- Signing: contract exists; real signing and verification remain pending.
- Notify idempotency: fake contract proves deterministic shape; real replay protection remains pending.
- Reconciliation: query contracts exist; reconciliation job remains pending.
- Amount/currency validation: amount/currency are captured in target and idempotency keys; provider compare remains pending.
- Order status transition: fake update previews exist; production transition rules remain pending.
- Rollback: disable mode or revert this contract while legacy payment fallback remains retained.

## Acceptance Artifacts

- `tests/test_d7_4_product_payment_adapter_contract.py`
- `tools/check_d7_4_product_payment_adapter_contract.py`
- Product smoke: `tools/product_management_gray_smoke.py`
- Commerce parity: `tools/compare_commerce_parity.py`

## Recommendation

D7.4 can enter adapter-contract acceptance after the scope isolation checker, D7.4 checker, focused tests, Product smoke, Commerce parity, and the six readonly parity checks pass. The next implementation stage is D7.5 only after this scope gate is green. Real WeChat Pay and Alipay calls must wait for a later sandbox/provider-evidence slice.
