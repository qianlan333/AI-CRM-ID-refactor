# D7 Slim Cleanup Report

This cleanup starts after #503 merged into `main`. It does not start D8, does not retire the legacy Flask shell, does not delete D7 blockers or legacy fallback, and does not enable real external or write behavior.

Root `aicrm_next/` remains the only Next production source. `experiments/ai_crm_next/src/aicrm_next/**` remains deleted and guarded by `scripts/check_no_duplicate_next_source.sh`.

## Inventory Summary

| category | path | line count | rg reference status | duplicated elsewhere? | decision | reason | risk | verification needed |
| --- | --- | ---: | --- | --- | --- | --- | --- | --- |
| D7 root adapter code | `aicrm_next/integration_gateway/media_adapters.py` | 265 | referenced by D7.1 checker/tests and media app boundary | no duplicate source under experiments | keep | core fake/disabled adapter boundary | medium | D7 tests, root suite |
| D7 root adapter code | `aicrm_next/integration_gateway/questionnaire_adapters.py` | 424 | referenced by D7.2 checker/tests and questionnaire app boundary | no duplicate source under experiments | keep | core fake OAuth/tag/webhook/submit side-effect boundary | high | D7 tests, root suite |
| D7 root adapter code | `aicrm_next/integration_gateway/user_ops_adapters.py` | 774 | referenced by D7.3 checker/tests and User Ops app boundary | no duplicate source under experiments | keep | core fake DND/batch/dispatch/deferred-job boundary | high | D7 tests, root suite |
| D7 root adapter code | `aicrm_next/integration_gateway/payment_adapters.py` | 479 | referenced by D7.4 checker/tests and commerce app boundary | no duplicate source under experiments | keep | core fake product/payment/notify/return boundary | critical | D7 tests, root suite |
| D7 root adapter code | `aicrm_next/integration_gateway/automation_adapters.py` | 426 | referenced by D7.5 checker/tests and automation app boundary | no duplicate source under experiments | keep | core fake automation/OpenClaw/runtime boundary | critical | D7 tests, root suite |
| D7 root adapter code | `aicrm_next/integration_gateway/customer_sync_adapters.py` | 415 | referenced by D7.6 checker/tests and customer sync boundary | no duplicate source under experiments | keep | core fake archive/contacts/identity/projection boundary | critical | D7 tests, root suite |
| D7 root adapter code | `aicrm_next/integration_gateway/mcp_openclaw_adapters.py` | 494 | referenced by D7.7 checker/tests and MCP/OpenClaw boundary | no duplicate source under experiments | keep | core fake MCP/OpenClaw compatibility boundary | critical | D7 tests, root suite |
| D7 contract files | `aicrm_next/integration_gateway/*_contracts.py` | 38-65 each | referenced by paired adapter tests/checkers | no duplicate source under experiments | keep | small typed contract surfaces used by fake adapters | medium | D7 tests |
| D7 source-of-truth docs | `docs/d7_write_external_blocker_matrix.md` | 31 | referenced by D6.5 checker and D7 planning tests | no | keep | source of blocker/delete-gate truth | critical | legacy checker, D7 planning test |
| D7 source-of-truth docs | `docs/d7_adapter_contract_catalog.md` | 40 | referenced by D7 planning checker/tests | no | keep | source of adapter contract truth | critical | D7 planning test |
| D7 source-of-truth docs | `docs/d7_capability_readiness_matrix.md` | 30 | referenced by D7 planning checker/tests | no | keep | source of current fake/staging readiness truth | critical | D7 planning test |
| D7 implementation reports | `docs/d7_1_media_adapter_implementation_report.md` | 72 | referenced by D7.1 checker/tests | repeats catalog themes, but includes acceptance evidence | keep | not deleted in this PR; future summary merge candidate | low | D7.1 checker/test |
| D7 implementation reports | `docs/d7_2_questionnaire_adapter_implementation_report.md` | 74 | referenced by D7.2 checker/tests | repeats catalog themes, but includes acceptance evidence | keep; fixture path updated | points to canonical experiments fixture path after dedupe | low | D7.2 checker/test |
| D7 implementation reports | `docs/d7_3_user_ops_adapter_implementation_report.md` | 84 | referenced by D7.3 checker/tests | repeats catalog themes, but includes acceptance evidence | keep | future summary merge candidate | low | D7.3 checker/test |
| D7 implementation reports | `docs/d7_4_product_payment_adapter_implementation_report.md` | 86 | referenced by D7.4 checker/tests | repeats catalog themes, but includes acceptance evidence | keep | future summary merge candidate | low | D7.4 checker/test |
| D7 implementation reports | `docs/d7_5_automation_adapter_implementation_report.md` | 99 | referenced by D7.5 checker/tests | repeats catalog themes, but includes acceptance evidence | keep | future summary merge candidate | low | D7.5 checker/test |
| D7 implementation reports | `docs/d7_6_archive_contacts_identity_adapter_implementation_report.md` | 95 | referenced by D7.6 checker/tests | repeats catalog themes, but includes acceptance evidence | keep; fixture path updated | points to canonical experiments fixture path after dedupe | low | D7.6 checker/test |
| D7 adapter contract docs | `docs/d7_*_adapter_contract.md` | 95-174 each | referenced by paired checker/tests | partially overlaps catalog, but has slice-specific safety rules | keep | do not flatten critical external systems into one hard-to-debug doc | medium | D7 focused tests |
| D7 checker tools | `tools/check_d7_1_media_adapter_contract.py` | 203 | referenced by `tests/test_d7_1_*` | checker boilerplate overlaps later D7 checkers | needs_manual_review | lower-risk future helper extraction possible, but not needed for duplicate cleanup | medium | all D7 tests |
| D7 checker tools | `tools/check_d7_2_questionnaire_adapter_contract.py` | 326 | referenced by `tests/test_d7_2_*` | checker boilerplate overlaps later D7 checkers | keep; fixture path updated | validates questionnaire-specific OAuth/tag/webhook safety | high | D7.2 test |
| D7 checker tools | `tools/check_d7_3_user_ops_adapter_contract.py` | 393 | referenced by `tests/test_d7_3_*` | checker boilerplate overlaps later D7 checkers | keep; fixture path updated | validates User Ops write/dispatch/deferred-job safety | high | D7.3 test |
| D7 checker tools | `tools/check_d7_4_product_payment_adapter_contract.py` | 419 | referenced by `tests/test_d7_4_*` | checker boilerplate overlaps later D7 checkers | keep; fixture path updated | validates product/payment safety; payment remains critical | critical | D7.4 test |
| D7 checker tools | `tools/check_d7_5_automation_adapter_contract.py` | 382 | referenced by `tests/test_d7_5_*` | checker boilerplate overlaps later D7 checkers | needs_manual_review | future shared helper candidate, but automation-specific safety is dense | critical | D7.5 test |
| D7 checker tools | `tools/check_d7_6_customer_sync_adapter_contract.py` | 374 | referenced by `tests/test_d7_6_*` | checker boilerplate overlaps later D7 checkers | keep; fixture path updated | validates archive/contacts/identity fake boundary | critical | D7.6 test |
| D7 checker tools | `tools/check_d7_7_mcp_openclaw_adapter_contract.py` | 368 | referenced by `tests/test_d7_7_*` | checker boilerplate overlaps later D7 checkers | keep; fixture path updated | validates MCP/OpenClaw fake boundary | critical | D7.7 test |
| D7 root parity/smoke tools | `tools/compare_commerce_parity.py` | 159 | referenced by D7.4 checker/tests | functionally overlaps experiments tool, not byte-identical | keep canonical | root tool is canonical for D7 checks | medium | D7.4 test, parity run |
| D7 root parity/smoke tools | `tools/compare_customer_read_model_parity.py` | 153 | referenced by D7.6/D7.7 checker/tests | functionally overlaps experiments tool, not byte-identical | keep canonical | root tool is canonical for D7 checks | medium | D7.6/D7.7 tests, parity run |
| D7 root parity/smoke tools | `tools/compare_questionnaire_parity.py` | 155 | referenced by D7.2 checker/tests | functionally overlaps experiments tool, not byte-identical | keep canonical | root tool is canonical for D7 checks | medium | D7.2 test, parity run |
| D7 root parity/smoke tools | `tools/compare_user_ops_parity.py` | 170 | referenced by D7.3 checker/tests | functionally overlaps experiments tool, not byte-identical | keep canonical | root tool is canonical for D7 checks | medium | D7.3 test, parity run |
| D7 root parity/smoke tools | `tools/*_readonly_gray_smoke.py`; `tools/product_management_gray_smoke.py` | 383-668 each | referenced by D7.4-D7.7 tests and legacy retirement assertions | functionally overlaps experiments tools, not byte-identical | keep canonical | canonical root smoke tools are used by root D7 checks | medium | root/experiments suites |
| D7 root fixtures | `tests/fixtures/old_commerce/*` | 6 files | referenced by root D7 docs/checkers/tests before this cleanup | byte-identical to experiments copy | delete | experiments fixtures are the single source of truth | low | D7.4 test, experiments suite |
| D7 root fixtures | `tests/fixtures/old_customer_read_model/*` | 5 files | referenced by root D7 docs/checkers/tests before this cleanup | byte-identical to experiments copy | delete | experiments fixtures are the single source of truth | low | D7.6/D7.7 tests, experiments suite |
| D7 root fixtures | `tests/fixtures/old_questionnaire/*` | 5 files | referenced by root D7 docs/checkers/tests before this cleanup | byte-identical to experiments copy | delete | experiments fixtures are the single source of truth | low | D7.2 test, experiments suite |
| D7 root fixtures | `tests/fixtures/old_user_ops/*` | 6 files | referenced by root D7 docs/checkers/tests before this cleanup | byte-identical to experiments copy | delete | experiments fixtures are the single source of truth | low | D7.3 test, experiments suite |
| D7 root fixtures | `tests/fixtures/old_automation_conversion/*` | 6 files | referenced by D7.5 checker/tests | same relative paths exist in experiments but SHA differs | keep | not a duplicate; do not collapse divergent evidence | medium | D7.5 tests |
| experiments parity/smoke tools | `experiments/ai_crm_next/tools/compare_*_parity.py`; `experiments/ai_crm_next/tools/*_smoke.py` | 12 files | heavily imported and monkeypatched by experiments tests | functionally overlaps root for 10 files; media tools exist only here | needs_manual_review | not byte-identical and experiments tests depend on internals; avoid risky wrapper conversion in this PR | medium | experiments pytest |
| experiments fixtures | `experiments/ai_crm_next/tests/fixtures/old_commerce/*` | 6 files | referenced by experiments tests and now root D7 checks | byte-identical to removed root copy | keep canonical | chosen single source of truth for old parity fixture data | low | root D7 tests, experiments pytest |
| experiments fixtures | `experiments/ai_crm_next/tests/fixtures/old_customer_read_model/*` | 5 files | referenced by experiments tests and now root D7 checks | byte-identical to removed root copy | keep canonical | chosen single source of truth for old parity fixture data | low | root D7 tests, experiments pytest |
| experiments fixtures | `experiments/ai_crm_next/tests/fixtures/old_questionnaire/*` | 5 files | referenced by experiments tests and now root D7 checks | byte-identical to removed root copy | keep canonical | chosen single source of truth for old parity fixture data | low | root D7 tests, experiments pytest |
| experiments fixtures | `experiments/ai_crm_next/tests/fixtures/old_user_ops/*` | 6 files | referenced by experiments tests and now root D7 checks | byte-identical to removed root copy | keep canonical | chosen single source of truth for old parity fixture data | low | root D7 tests, experiments pytest |
| experiments fixtures | `experiments/ai_crm_next/tests/fixtures/old_media_library/*` | 3 files | referenced by media experiments tests/tools | no root copy | keep | only fixture source for media experiment parity | low | experiments pytest |
| tests that depend on D7 adapters/checkers | `tests/test_d7_*.py` | 10 files | direct root D7 acceptance coverage | no duplicate test source | keep | focused safety coverage is still needed | medium | D7 focused tests |

## Actions Taken

- Removed the byte-identical root fixture copies under:
  - `tests/fixtures/old_commerce/`
  - `tests/fixtures/old_customer_read_model/`
  - `tests/fixtures/old_questionnaire/`
  - `tests/fixtures/old_user_ops/`
- Updated root D7 docs, checkers, and tests to read those fixtures from `experiments/ai_crm_next/tests/fixtures/old_*`.
- Kept `tests/fixtures/old_automation_conversion/` because SHA comparison showed it differs from the experiments fixture set.
- Kept root adapter and contract code. These files are D7's fake/disabled adapter boundary, not duplicate source.
- Kept D7 source-of-truth docs: blocker matrix, adapter contract catalog, and readiness matrix.
- Did not convert experiments parity/smoke tools to wrappers in this PR because they are not byte-identical, media tools have no root counterpart, and experiments tests monkeypatch internal functions. They remain a future `needs_manual_review` consolidation item.

## Evidence

- Duplicate fixture SHA evidence: `old_commerce`, `old_customer_read_model`, `old_questionnaire`, and `old_user_ops` matched exactly between root and experiments before deletion.
- Divergent fixture evidence: all `old_automation_conversion` root files had different SHA-256 values from the experiments copies.
- Tool evidence: root and experiments parity/smoke tools with matching names were not byte-identical; all overlapping files had different SHA-256 values.
- Duplicate source evidence: `find experiments/ai_crm_next -path '*/src/aicrm_next*' -print` has no output.

## Safety

- No D8 work.
- No production/deploy/nginx/systemd runtime config changes.
- No real traffic cutover.
- No real external service calls.
- No write endpoints executed.
- No D7 blocker deleted.
- No legacy fallback deleted.
- No forbidden production-approval or delete-readiness marker introduced.
