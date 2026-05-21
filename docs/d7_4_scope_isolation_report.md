# D7.4 Scope Isolation Report

This report isolates the D7.4 Product/Payment adapter-contract increment from the accepted D7.1-D7.3 adapter prerequisites.

Root `aicrm_next/` is the only Next production source. No D7 scope includes, mirrors, or recreates `experiments/ai_crm_next/src/aicrm_next/**`.

## D7.4 Intended Scope

D7.4 is limited to fake or disabled Product/Commerce adapter boundaries:

- Product write intent through `ProductWriteGateway`
- WeChat Pay checkout and notify shape through `WeChatPayAdapter` and `PaymentNotifyGateway`
- Alipay checkout, notify, and return shape through `AlipayAdapter`, `PaymentNotifyGateway`, and `PaymentReturnGateway`
- Shared fake idempotency and in-memory audit use
- Product smoke and Commerce parity evidence
- Documentation/checker/test coverage proving no provider execution and no production config change

## D7.4 Actual Changed Files

The D7.4 baseline contains D7.1-D7.4 because earlier accepted prerequisites were merged before this increment. The D7.4 increment itself is the Product/Payment subset listed under `D7.4 increment files`; all other files are classified as accepted prerequisites or shared scope documentation.

## File Classification

### D7.1 baseline files

- `aicrm_next/integration_gateway/audit.py`
- `aicrm_next/integration_gateway/idempotency.py`
- `aicrm_next/integration_gateway/media_adapters.py`
- `aicrm_next/integration_gateway/media_contracts.py`
- `aicrm_next/media_library/application.py`

### D7.2 baseline files

- `aicrm_next/integration_gateway/questionnaire_adapters.py`
- `aicrm_next/integration_gateway/questionnaire_contracts.py`
- `aicrm_next/questionnaire/application.py`
- `aicrm_next/questionnaire/oauth.py`

### D7.3 baseline files

- `aicrm_next/integration_gateway/dispatch.py`
- `aicrm_next/integration_gateway/user_ops_adapters.py`
- `aicrm_next/integration_gateway/user_ops_contracts.py`
- `aicrm_next/ops_enrollment/api.py`
- `aicrm_next/ops_enrollment/application.py`

### D7.4 increment files

- `aicrm_next/integration_gateway/payment_adapters.py`
- `aicrm_next/integration_gateway/payment_contracts.py`
- `aicrm_next/commerce/api.py`
- `aicrm_next/commerce/application.py`

### Shared infrastructure files

- `aicrm_next/integration_gateway/audit.py`
- `aicrm_next/integration_gateway/idempotency.py`

### docs/tests/checkers

- `docs/d7_1_media_storage_wecom_media_adapter_contract.md`
- `docs/d7_1_media_adapter_implementation_report.md`
- `docs/d7_2_questionnaire_submit_oauth_wecom_tag_adapter_contract.md`
- `docs/d7_2_questionnaire_adapter_implementation_report.md`
- `docs/d7_3_user_ops_dnd_batch_send_wecom_dispatch_adapter_contract.md`
- `docs/d7_3_user_ops_adapter_implementation_report.md`
- `docs/d7_4_product_payment_adapter_contract.md`
- `docs/d7_4_product_payment_adapter_implementation_report.md`
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
- `tools/check_d7_1_media_adapter_contract.py`
- `tools/check_d7_2_questionnaire_adapter_contract.py`
- `tools/check_d7_3_user_ops_adapter_contract.py`
- `tools/check_d7_4_product_payment_adapter_contract.py`
- `tools/check_d7_scope_isolation.py`
- `tools/compare_commerce_parity.py`
- `tools/compare_questionnaire_parity.py`
- `tools/compare_user_ops_parity.py`
- `tools/product_management_gray_smoke.py`
- `tools/questionnaire_readonly_gray_smoke.py`
- `tools/user_ops_readonly_gray_smoke.py`
- `tests/test_d7_1_media_adapter_contract.py`
- `tests/test_d7_2_questionnaire_adapter_contract.py`
- `tests/test_d7_3_user_ops_adapter_contract.py`
- `tests/test_d7_4_product_payment_adapter_contract.py`
- `tests/test_d7_scope_isolation.py`
- `experiments/ai_crm_next/tests/fixtures/old_commerce/alipay_transactions.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_commerce/checkout_alipay.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_commerce/checkout_wechat.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_commerce/product_detail.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_commerce/products.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_commerce/wechat_transactions.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_questionnaire/admin_detail.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_questionnaire/admin_list.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_questionnaire/admin_preflight.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_questionnaire/public_get.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_questionnaire/submit.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_user_ops/list.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_user_ops/list.not_added.json`
- `experiments/ai_crm_next/tests/fixtures/old_user_ops/list.wecom_added.json`
- `experiments/ai_crm_next/tests/fixtures/old_user_ops/overview.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_user_ops/preview.default.json`
- `experiments/ai_crm_next/tests/fixtures/old_user_ops/send_records.default.json`

### out-of-scope files

- none

## Prerequisite Files Present In Dirty Diff

D7.1-D7.3 prerequisite files are present because their accepted adapter-contract work is still in the same dirty worktree. These files do not count as D7.4 scope expansion because they are explicitly marked as `accepted_prerequisite` in `docs/d7_adapter_baseline_summary.md` and are grouped as D7.1-D7.3 baseline files above.

## Scope Questions

| question | answer | evidence |
| --- | --- | --- |
| Does D7.4 modify modules outside payment, commerce, or integration gateway? | No for the D7.4 current increment. Other changed modules belong to accepted D7.1-D7.3 prerequisites. | `D7.4 increment files` contains only root commerce and payment integration files. |
| Does D7.4 modify deploy or production config? | No. | No `deploy/`, nginx, systemd, supervisor, Docker, or production config path is in the D7.4 increment. |
| Does D7.4 trigger real outbound calls? | No. | Product/Payment adapters return fake/staging-disabled results and `side_effect_executed=false`. |
| Does D7.4 process real payment notify callbacks? | No. | `PaymentNotifyGateway` builds fake notify and order-update previews only. |
| Does D7.4 break the six parity groups? | No known break from this scope. | User Ops, Questionnaire, Commerce, and Media D7 checkers/parity are covered by current tools; Customer Read Model and Automation are not touched by the D7.4 increment. |

## Why Prerequisites Are Not D7.4 Overreach

D7.4 depends on shared audit/idempotency and the adapter-contract vocabulary established in D7.1-D7.3. The D7.4 Product/Payment work reuses those boundaries rather than editing D7.1-D7.3 behavior. Reviewers should treat prerequisite files as baseline evidence and evaluate D7.4 only against the Product/Payment increment plus the scope isolation artifacts.

## PR Delivery Recommendation

Recommended delivery order:

1. Review D7.1-D7.3 as accepted prerequisites or previously approved commits.
2. Review D7.4 Product/Payment as the current increment.
3. Include `tools/check_d7_scope_isolation.py` and `tests/test_d7_scope_isolation.py` in the D7.4 review gate.
4. If practical, split PRs by D7.1, D7.2, D7.3, and D7.4. If not, keep the combined PR but require the scope checker output and this report in the acceptance notes.

Do not enter D7.5 until the scope checker and D7.4 checker pass.
