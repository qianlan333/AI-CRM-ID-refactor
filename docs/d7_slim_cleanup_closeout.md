# D7 Slim Cleanup Closeout

Date: 2026-05-21

Scope: closeout-only status check after the D7 slim cleanup and parity/smoke dedupe work. This report does not start D8, does not remove D7 adapter boundary code, and does not remove legacy fallback or D7 blocker files.

## Summary

| Area | Evidence | Decision |
| --- | --- | --- |
| Duplicate Next source | `find experiments/ai_crm_next -path '*/src/aicrm_next*' -print` returned no paths. | Keep guard; no cleanup needed. |
| Old fixtures | Cross-tree SHA scan between `tests/fixtures/old_*` and `experiments/ai_crm_next/tests/fixtures/old_*` found 0 byte-identical matches. | No fixture deletion needed. |
| Automation fixtures | Six matching automation fixture paths remain in both trees, but every pair has a different SHA and size. | Intentionally kept as divergent parity evidence. |
| Parity/smoke tools | Root `tools/` contains the canonical implementations; all 12 experiments parity/smoke entries are 12-line wrappers using `_root_tool_wrapper.py`. | Intentionally kept for CLI path compatibility. |
| D7.5-D7.7 checkers | `check_d7_5`, `check_d7_6`, and `check_d7_7` import `tools.d7_contract_check_common`. | Shared helper extraction is in place; no further closeout edit needed. |
| D7 docs and reports | Implementation reports are short historical summaries and adapter contracts are still referenced by focused tests/checkers. | Intentionally kept; no report deletion in this closeout. |
| D7 adapter boundary | `aicrm_next/integration_gateway/*_adapters.py` and `*_contracts.py` remain D7 contract boundary files. | Intentionally kept. |

## Fixture Closeout

Cross-tree byte-identical duplicate count: 0.

Remaining same-path automation fixture pairs are divergent, so they are not duplicate cleanup candidates:

| Root fixture | Experiments fixture | Root SHA prefix | Experiments SHA prefix | Decision |
| --- | --- | --- | --- | --- |
| `tests/fixtures/old_automation_conversion/activation_webhook.default.json` | `experiments/ai_crm_next/tests/fixtures/old_automation_conversion/activation_webhook.default.json` | `9be655d64bea` | `c91ed3fa487e` | Keep divergent fixtures. |
| `tests/fixtures/old_automation_conversion/execution_records.default.json` | `experiments/ai_crm_next/tests/fixtures/old_automation_conversion/execution_records.default.json` | `4994829002df` | `41a70874345e` | Keep divergent fixtures. |
| `tests/fixtures/old_automation_conversion/member_detail.default.json` | `experiments/ai_crm_next/tests/fixtures/old_automation_conversion/member_detail.default.json` | `94203a2ba2fa` | `4006722e5aae` | Keep divergent fixtures. |
| `tests/fixtures/old_automation_conversion/members.default.json` | `experiments/ai_crm_next/tests/fixtures/old_automation_conversion/members.default.json` | `35534f381930` | `0ec52b95735c` | Keep divergent fixtures. |
| `tests/fixtures/old_automation_conversion/overview.default.json` | `experiments/ai_crm_next/tests/fixtures/old_automation_conversion/overview.default.json` | `3b72cc0771d5` | `6eb3236720fc` | Keep divergent fixtures. |
| `tests/fixtures/old_automation_conversion/pools.default.json` | `experiments/ai_crm_next/tests/fixtures/old_automation_conversion/pools.default.json` | `be7294350c0c` | `7546d907b20d` | Keep divergent fixtures. |

## Parity/Smoke Closeout

Root canonical parity tools:

| Tool | Lines | Experiments status |
| --- | ---: | --- |
| `tools/compare_automation_conversion_parity.py` | 139 | 12-line wrapper. |
| `tools/compare_commerce_parity.py` | 164 | 12-line wrapper. |
| `tools/compare_customer_read_model_parity.py` | 158 | 12-line wrapper. |
| `tools/compare_media_library_parity.py` | 120 | 12-line wrapper. |
| `tools/compare_questionnaire_parity.py` | 160 | 12-line wrapper. |
| `tools/compare_user_ops_parity.py` | 175 | 12-line wrapper. |

Root canonical smoke tools:

| Tool | Lines | Experiments status |
| --- | ---: | --- |
| `tools/automation_readonly_gray_smoke.py` | 510 | 12-line wrapper. |
| `tools/customer_read_model_gray_smoke.py` | 467 | 12-line wrapper. |
| `tools/media_library_gray_smoke.py` | 394 | 12-line wrapper. |
| `tools/product_management_gray_smoke.py` | 444 | 12-line wrapper. |
| `tools/questionnaire_readonly_gray_smoke.py` | 673 | 12-line wrapper. |
| `tools/user_ops_readonly_gray_smoke.py` | 420 | 12-line wrapper. |

The experiments wrappers contain no parity/smoke business logic definitions, no TestClient setup, and no direct HTTP client implementation. They only bootstrap the repository path and delegate to the root canonical tool module.

## Checker Closeout

| Checker | Shared helper status | Ability-specific assertions |
| --- | --- | --- |
| `tools/check_d7_5_automation_adapter_contract.py` | Imports `tools.d7_contract_check_common`. | Automation application boundary, OpenClaw dispatch, workflow runtime, agent runtime, and guarded fake operation checks remain local. |
| `tools/check_d7_6_customer_sync_adapter_contract.py` | Imports `tools.d7_contract_check_common`. | Archive, contacts, identity, source guard, and fake sync checks remain local. |
| `tools/check_d7_7_mcp_openclaw_adapter_contract.py` | Imports `tools.d7_contract_check_common`. | MCP/OpenClaw adapter, legacy gate, source guard, and fake operation checks remain local. |

## Intentionally Kept

- D7 adapter contract files and `aicrm_next/integration_gateway/*_adapters.py` / `*_contracts.py`: kept as the D7 boundary under test.
- D7 implementation reports: kept as compact historical summaries rather than current cleanup candidates.
- D7 blocker matrix, readiness matrix, and adapter catalog: kept as source-of-truth safety documents.
- Legacy fallback files, including payment, OAuth, WeCom, OpenClaw, archive, contacts, identity, and workflow fallback surfaces: kept blocked and untouched.

## Closeout Decision

No obvious byte-identical D7 duplication remains after the #509 parity/smoke dedupe. This closeout adds status documentation only; it does not delete adapter code, tests, checkers, legacy fallback, or D7 blocker files.
