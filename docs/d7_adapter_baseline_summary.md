# D7 Adapter Baseline Summary

This summary captures the current D7.1-D7.4 adapter-contract baseline after #502. It is a scope and evidence document only. It does not authorize real external calls, production traffic changes, legacy fallback deletion, or payment-provider execution.

Root `aicrm_next/` is the only Next production source. D7 implementation files live only under root `aicrm_next/`, docs, tools, tests, and fixtures. `experiments/ai_crm_next/src/aicrm_next/**` remains deleted and must not be recreated.

## Stage Summary

| stage | capability | status | core_files | docs | checker | tests | verification | scope_status | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D7.1 | Media storage / WeCom media adapter contract | accepted_prerequisite | `aicrm_next/integration_gateway/media_contracts.py`; `aicrm_next/integration_gateway/media_adapters.py`; `aicrm_next/media_library/application.py` | `docs/d7_1_media_storage_wecom_media_adapter_contract.md`; `docs/d7_1_media_adapter_implementation_report.md` | `tools/check_d7_1_media_adapter_contract.py` | `tests/test_d7_1_media_adapter_contract.py` | Checker exercises fake, disabled, staging, guarded production modes, idempotency, audit, and media parity static evidence. | accepted_prerequisite | Real cloud upload and real WeCom media upload remain blocked. |
| D7.2 | Questionnaire submit / OAuth / WeCom tag / external push adapter contract | accepted_prerequisite | `aicrm_next/integration_gateway/questionnaire_contracts.py`; `aicrm_next/integration_gateway/questionnaire_adapters.py`; `aicrm_next/questionnaire/application.py`; `aicrm_next/questionnaire/oauth.py` | `docs/d7_2_questionnaire_submit_oauth_wecom_tag_adapter_contract.md`; `docs/d7_2_questionnaire_adapter_implementation_report.md` | `tools/check_d7_2_questionnaire_adapter_contract.py` | `tests/test_d7_2_questionnaire_adapter_contract.py`; `experiments/ai_crm_next/tests/fixtures/old_questionnaire/*` | Checker and tests cover fake OAuth identity, tag operation, webhook intent, submit side-effect boundary, no provider call, and questionnaire parity. | accepted_prerequisite | Real OAuth, WeCom tag writes, and webhook delivery remain blocked. |
| D7.3 | User Ops DND / batch-send / WeCom dispatch / deferred jobs adapter contract | accepted_prerequisite | `aicrm_next/integration_gateway/user_ops_contracts.py`; `aicrm_next/integration_gateway/user_ops_adapters.py`; `aicrm_next/integration_gateway/dispatch.py`; `aicrm_next/ops_enrollment/application.py`; `aicrm_next/ops_enrollment/api.py` | `docs/d7_3_user_ops_dnd_batch_send_wecom_dispatch_adapter_contract.md`; `docs/d7_3_user_ops_adapter_implementation_report.md` | `tools/check_d7_3_user_ops_adapter_contract.py` | `tests/test_d7_3_user_ops_adapter_contract.py`; `experiments/ai_crm_next/tests/fixtures/old_user_ops/*` | Checker and tests cover fake DND, batch-send, WeCom dispatch, deferred jobs, idempotency, audit, and User Ops parity. | accepted_prerequisite | Real DND writes, WeCom dispatch, and deferred job execution remain blocked. |
| D7.4 | Product writes / WeChat Pay / Alipay / notify / return adapter contract | scope_isolated | `aicrm_next/integration_gateway/payment_contracts.py`; `aicrm_next/integration_gateway/payment_adapters.py`; `aicrm_next/commerce/application.py`; `aicrm_next/commerce/api.py` | `docs/d7_4_product_payment_adapter_contract.md`; `docs/d7_4_product_payment_adapter_implementation_report.md`; `docs/d7_4_scope_isolation_report.md` | `tools/check_d7_4_product_payment_adapter_contract.py`; `tools/check_d7_scope_isolation.py` | `tests/test_d7_4_product_payment_adapter_contract.py`; `tests/test_d7_scope_isolation.py`; `experiments/ai_crm_next/tests/fixtures/old_commerce/*` | D7.4 checker, scope checker, Product smoke, Commerce parity, and focused tests validate guarded fake contract behavior with no payment-provider call. | current_increment | D7.4 is the current increment on top of accepted D7.1-D7.3 prerequisites. |

## File Lists By Stage

### D7.1 accepted_prerequisite

- `aicrm_next/integration_gateway/audit.py`
- `aicrm_next/integration_gateway/idempotency.py`
- `aicrm_next/integration_gateway/media_adapters.py`
- `aicrm_next/integration_gateway/media_contracts.py`
- `aicrm_next/media_library/application.py`
- `docs/d7_1_media_storage_wecom_media_adapter_contract.md`
- `docs/d7_1_media_adapter_implementation_report.md`
- `tools/check_d7_1_media_adapter_contract.py`
- `tests/test_d7_1_media_adapter_contract.py`

### D7.2 accepted_prerequisite

- `aicrm_next/integration_gateway/questionnaire_adapters.py`
- `aicrm_next/integration_gateway/questionnaire_contracts.py`
- `aicrm_next/questionnaire/application.py`
- `aicrm_next/questionnaire/oauth.py`
- `docs/d7_2_questionnaire_submit_oauth_wecom_tag_adapter_contract.md`
- `docs/d7_2_questionnaire_adapter_implementation_report.md`
- `tools/check_d7_2_questionnaire_adapter_contract.py`
- `tools/compare_questionnaire_parity.py`
- `tools/questionnaire_readonly_gray_smoke.py`
- `tests/test_d7_2_questionnaire_adapter_contract.py`
- `experiments/ai_crm_next/tests/fixtures/old_questionnaire/admin_detail.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_questionnaire/admin_list.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_questionnaire/admin_preflight.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_questionnaire/public_get.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_questionnaire/submit.default.json`

### D7.3 accepted_prerequisite

- `aicrm_next/integration_gateway/dispatch.py`
- `aicrm_next/integration_gateway/user_ops_adapters.py`
- `aicrm_next/integration_gateway/user_ops_contracts.py`
- `aicrm_next/ops_enrollment/api.py`
- `aicrm_next/ops_enrollment/application.py`
- `docs/d7_3_user_ops_dnd_batch_send_wecom_dispatch_adapter_contract.md`
- `docs/d7_3_user_ops_adapter_implementation_report.md`
- `tools/check_d7_3_user_ops_adapter_contract.py`
- `tools/compare_user_ops_parity.py`
- `tools/user_ops_readonly_gray_smoke.py`
- `tests/test_d7_3_user_ops_adapter_contract.py`
- `experiments/ai_crm_next/tests/fixtures/old_user_ops/list.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_user_ops/list.not_added.json`
- `experiments/ai_crm_next/tests/fixtures/old_user_ops/list.wecom_added.json`
- `experiments/ai_crm_next/tests/fixtures/old_user_ops/overview.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_user_ops/preview.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_user_ops/send_records.default.json`

### D7.4 current_increment

- `aicrm_next/integration_gateway/payment_adapters.py`
- `aicrm_next/integration_gateway/payment_contracts.py`
- `aicrm_next/commerce/api.py`
- `aicrm_next/commerce/application.py`
- `docs/d7_4_product_payment_adapter_contract.md`
- `docs/d7_4_product_payment_adapter_implementation_report.md`
- `tools/check_d7_4_product_payment_adapter_contract.py`
- `tools/compare_commerce_parity.py`
- `tools/product_management_gray_smoke.py`
- `tests/test_d7_4_product_payment_adapter_contract.py`
- `experiments/ai_crm_next/tests/fixtures/old_commerce/alipay_transactions.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_commerce/checkout_alipay.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_commerce/checkout_wechat.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_commerce/product_detail.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_commerce/products.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_commerce/wechat_transactions.default.json`

### Shared D7 documentation and scope isolation

- `docs/d7_adapter_contract_catalog.md`
- `docs/d7_adapter_baseline_summary.md`
- `docs/d7_capability_readiness_matrix.md`
- `docs/d7_write_external_blocker_matrix.md`
- `docs/d7_4_scope_isolation_report.md`
- `docs/go_no_go_checklist.md`
- `docs/legacy_delete_batches.md`
- `docs/legacy_retirement_plan.md`
- `docs/legacy_route_owner_cutover_matrix.md`
- `docs/module_status_matrix.md`
- `docs/remaining_work_queue.md`
- `tools/check_d7_scope_isolation.py`
- `tests/test_d7_scope_isolation.py`

## Acceptance Conclusions

| stage | acceptance_conclusion | checker_test_parity_summary |
| --- | --- | --- |
| D7.1 | Accepted as prerequisite for later D7 adapter slices. | D7.1 checker and tests cover fake media contracts, audit, idempotency, guarded production mode, no remote URL fetch, and media parity static evidence. |
| D7.2 | Accepted as prerequisite for later D7 adapter slices. | D7.2 checker and tests cover fake submit side effects, OAuth, tag, webhook boundaries, questionnaire smoke/parity fixtures, and no provider calls. |
| D7.3 | Accepted as prerequisite for D7.4 Product/Payment isolation. | D7.3 checker and tests cover fake DND, batch-send, dispatch, deferred jobs, User Ops smoke/parity fixtures, and no WeCom dispatch. |
| D7.4 | Current increment is scope-isolated for adapter-contract acceptance. | D7.4 checker and tests cover ProductWriteGateway, WeChatPayAdapter, AlipayAdapter, PaymentNotifyGateway, PaymentReturnGateway, Product smoke, Commerce parity, and no payment-provider call. |

## Why The Worktree Contains Mixed D7.1-D7.4 Diff

The current branch accumulated D7 adapter-contract work in order: D7.1 introduced shared audit/idempotency and media adapters; D7.2 reused those helpers for questionnaire boundaries; D7.3 added User Ops boundaries; D7.4 then added Product/Payment boundaries. The earlier D7.1-D7.3 files were already accepted but remained in the same uncommitted dirty worktree, so the visible diff contains both prerequisite baseline files and the D7.4 current increment.

## Mixed Diff Acceptability

The mixed diff is acceptable for D7.4 scope isolation only if the prerequisite and increment files remain explicitly classified and the checker stays green. It is not acceptable to describe the whole dirty diff as a pure D7.4 feature diff. The correct interpretation is:

- D7.1-D7.3: accepted_prerequisite
- D7.4: current_increment
- Shared docs/checkers: scope explanation and guardrails
- Out-of-scope files: none

## PR And Merge Recommendation

Prefer splitting delivery by stage if the review workflow can still isolate commits cleanly. If the repository workflow keeps the current branch as the delivery unit, use this baseline summary and the D7.4 scope isolation report as review evidence, then squash or merge in chronological order with D7.1-D7.3 prerequisites clearly named before D7.4. Do not rewrite published history without explicit maintainer approval.
