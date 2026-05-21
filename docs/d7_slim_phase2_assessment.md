# D7 Slim Phase 2 Assessment

## Scope

This assessment starts from `origin/main` after PR #504. It is intentionally
read-only in behavior: no D8 work, no legacy fallback deletion, no adapter code
deletion, no duplicate Next source restoration, no production/deploy/nginx/systemd
configuration changes, and no real external or write endpoint execution.

Root `aicrm_next/` remains the only Next production source. The deleted
`experiments/ai_crm_next/src/aicrm_next/` tree must remain absent.

## Summary Decision

| Area | Evidence | Decision | Risk | Next safe action |
| --- | --- | --- | --- | --- |
| D7 checker boilerplate | `tools/check_d7_5_automation_adapter_contract.py`, `tools/check_d7_6_customer_sync_adapter_contract.py`, and `tools/check_d7_7_mcp_openclaw_adapter_contract.py` repeat the same path/read/sample-call/mode/idempotency/docs/source-guard/report patterns. D7.1-D7.4 share smaller helpers but have more slice-specific runtime checks. | `consolidate_candidate` | Medium. These checkers encode safety gates and test expectations. A careless helper extraction could weaken per-capability diagnostics. | Extract a tiny shared helper only for mechanical file/path/source/report helpers, then rerun all `tests/test_d7_*.py` and the root suite. |
| D7 implementation reports | D7.1-D7.6 reports repeat catalog/readiness safety language, but each is directly referenced by checker/tests and preserves slice-specific validation evidence. | `consolidate_candidate` with `needs_manual_review` for deletion | Medium. Removing or shortening reports before updating checker/test references would break current status assertions and lose historical acceptance evidence. | Keep source-of-truth docs as blocker matrix, contract catalog, and readiness matrix. Later shorten per-slice reports into evidence notes or fold stable summaries into `docs/d7_adapter_baseline_summary.md`. |
| Root vs experiments parity/smoke tools | Ten overlapping tools differ only in import-path bootstrap. Experiments tests import those modules directly, monkeypatch internals, and some root legacy tests inspect experiments tool source text. | `needs_manual_review` for wrapperization | Medium to high. Thin wrappers are feasible, but source-text assertions and monkeypatch behavior make a direct replacement risky. | Convert one low-risk parity tool first, update tests from source-token assertions to runtime safety assertions, then expand only after experiments pytest and root D7 tests pass. |

## 1. D7 Checker Boilerplate Assessment

### Inventory

| Path | Lines | Reference status | Duplicated elsewhere? | Decision | Reason | Risk | Verification needed |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| `tools/check_d7_1_media_adapter_contract.py` | 203 | Referenced by D7 media tests and PR/check workflows through direct command usage. | Partial helper overlap: `_read`, `_class_methods`, production-config diff checks, report writer. | Keep; small helper candidate | Media checks are shorter and include D7.1-specific safety assertions. | Low to medium | `python3 -m pytest -q tests/test_d7_1_media_adapter_contract.py` plus root suite |
| `tools/check_d7_2_questionnaire_adapter_contract.py` | 326 | Referenced by D7 questionnaire tests and contract docs. | Partial overlap with D7.3/D7.4 runtime/smoke/parity/report flow. | Keep; small helper candidate | Questionnaire-specific smoke/parity coverage should remain easy to diagnose. | Medium | `python3 -m pytest -q tests/test_d7_2_questionnaire_adapter_contract.py` plus experiments suite |
| `tools/check_d7_3_user_ops_adapter_contract.py` | 393 | Referenced by D7 user-ops tests. | Partial overlap with D7.2/D7.4 and generic JSON/Markdown report writers. | Keep; small helper candidate | User Ops has specific DND/batch/deferred/dispatch safety boundaries. | Medium | `python3 -m pytest -q tests/test_d7_3_user_ops_adapter_contract.py` plus parity/smoke tools |
| `tools/check_d7_4_product_payment_adapter_contract.py` | 419 | Referenced by D7 product/payment tests and D7 scope isolation checks. | Partial overlap with D7.2/D7.3; has unique environment setup and payment safety checks. | Keep; helper only for mechanical writers/path helpers | Payment boundaries are high risk and should keep capability-specific checks visible. | Medium to high | `python3 -m pytest -q tests/test_d7_4_product_payment_adapter_contract.py tests/test_d7_scope_isolation.py` |
| `tools/check_d7_5_automation_adapter_contract.py` | 382 | Referenced by D7 automation tests. | High overlap with D7.6/D7.7: `_path`, `_read`, `_sample_call`, mode checks, idempotency/audit checks, docs checks, source guards, report writers. | Consolidate candidate | This is the clearest helper-extraction cluster. | Medium | D7.5-D7.7 tests plus root suite |
| `tools/check_d7_6_customer_sync_adapter_contract.py` | 374 | Referenced by D7 archive/contacts/identity tests. | High overlap with D7.5/D7.7. | Consolidate candidate | Shared mechanics can move to a helper while keeping archive/contacts/identity rules local. | Medium | D7.6 tests plus legacy fallback import checks |
| `tools/check_d7_7_mcp_openclaw_adapter_contract.py` | 368 | Referenced by D7 MCP/OpenClaw tests. | High overlap with D7.5/D7.6, plus OpenClaw-specific gate checks. | Consolidate candidate | Shared mechanics are extractable, but OpenClaw gate checks should stay local. | Medium | D7.7 tests plus duplicate-source guard |
| `tools/check_d7_replacement_planning.py` | 242 | Planning/status checker. | Not the same shape as per-capability contract checkers. | Keep | It validates planning boundaries, not an adapter slice. | Low | Existing focused test if present plus root suite |
| `tools/check_d7_scope_isolation.py` | 253 | Referenced by D7 scope isolation tests. | Not a direct duplicate of per-capability checkers. | Keep | It enforces cross-scope safety and should remain separate for diagnostic clarity. | Low | `python3 -m pytest -q tests/test_d7_scope_isolation.py` |

### Helper Feasibility

A future helper such as `tools/d7_contract_check_common.py` is feasible if it is
kept narrow. Safe helper candidates:

- path resolution and text reading
- class-method extraction helpers
- sample-call formatting helpers
- repeated Markdown/JSON report writer primitives
- source token scan helpers with explicit per-slice inputs

Do not collapse all D7 checkers into one generic checker. The current separation
still helps locate failures by capability and prevents payment/OAuth/WeCom/
OpenClaw/archive/contacts/identity boundaries from becoming less visible.

## 2. D7 Implementation Report Assessment

### Inventory

| Path | Lines | Reference status | Duplicated elsewhere? | Decision | Reason | Risk | Verification needed |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| `docs/d7_1_media_adapter_implementation_report.md` | 72 | Referenced by `tools/check_d7_1_media_adapter_contract.py` and `tests/test_d7_1_media_adapter_contract.py`. | Partially repeats catalog/readiness safety language. | Keep; shorten candidate | It contains D7.1 acceptance evidence and direct checker/test expectations. | Medium | D7.1 tests and checker |
| `docs/d7_2_questionnaire_adapter_implementation_report.md` | 74 | Referenced by D7.2 checker and tests. | Partially repeats catalog/readiness safety language. | Keep; shorten candidate | It preserves questionnaire-specific validation and fallback boundaries. | Medium | D7.2 tests and checker |
| `docs/d7_3_user_ops_adapter_implementation_report.md` | 84 | Referenced by D7.3 checker and tests. | Repeats catalog/readiness summaries more heavily than D7.1-D7.2. | Consolidate candidate | Likely reducible into a short evidence note once tests stop requiring standalone status wording. | Medium | D7.3 tests and parity/smoke tools |
| `docs/d7_4_product_payment_adapter_implementation_report.md` | 86 | Referenced by D7.4 checker, D7.4 tests, and scope isolation tests. | Repeats catalog/readiness and payment safety boundaries. | Keep until manual review | Payment safety evidence is high risk; shortening should preserve explicit no-real-charge/no-notify boundaries. | High | D7.4 tests, scope isolation, payment fallback presence checks |
| `docs/d7_5_automation_adapter_implementation_report.md` | 99 | Referenced by D7.5 checker and tests. | Repeats baseline summary, readiness matrix, and contract catalog content. | Consolidate candidate | Good candidate to fold stable summary into `docs/d7_adapter_baseline_summary.md`, leaving only evidence notes. | Medium | D7.5 tests and checker |
| `docs/d7_6_archive_contacts_identity_adapter_implementation_report.md` | 95 | Referenced by D7.6 checker and tests. | Repeats baseline summary, readiness matrix, and contract catalog content. | Consolidate candidate with manual review | Archive/contacts/identity fallback boundaries are explicitly protected, so evidence must not be lost. | Medium to high | D7.6 tests and fallback protected-file checks |

### Documentation Source of Truth

The stable D7 source-of-truth docs should remain:

- `docs/d7_write_external_blocker_matrix.md`
- `docs/d7_adapter_contract_catalog.md`
- `docs/d7_capability_readiness_matrix.md`
- `docs/d7_adapter_baseline_summary.md`

The per-slice implementation reports can be shortened later, but not deleted in
this assessment branch. Several tests and checkers still assert their presence,
so consolidation should be done in a follow-up that updates those assertions
together with the docs.

## 3. Parity And Smoke Tool Wrapper Assessment

Phase 2B result: root `tools/` is now the canonical source for D7 parity and
smoke tools. The experiments paths remain for command compatibility, but they
load the root tool modules through thin wrappers instead of carrying duplicated
logic.

### Overlapping Tools

The following root and experiments tools are functionally duplicated. A diff
shows the only current difference is import-path bootstrap: root tools add the
repository root directly, while experiments tools compute the parent repository
root from `experiments/ai_crm_next`.

| Root path | Experiments path | Lines root/experiments | Duplicated elsewhere? | Decision | Reason | Risk | Verification needed |
| --- | --- | ---: | --- | --- | --- | --- | --- |
| `tools/compare_automation_conversion_parity.py` | `experiments/ai_crm_next/tools/compare_automation_conversion_parity.py` | 139/12 | Yes, experiments is now wrapper only | Done | Root tool is canonical; experiments path loads root module. | Low | Automation parity plus experiments pytest |
| `tools/compare_commerce_parity.py` | `experiments/ai_crm_next/tools/compare_commerce_parity.py` | 164/12 | Yes, experiments is now wrapper only | Done | Root tool is canonical; experiments path loads root module. | Medium | Commerce parity, payment D7 tests, experiments pytest |
| `tools/compare_customer_read_model_parity.py` | `experiments/ai_crm_next/tools/compare_customer_read_model_parity.py` | 158/12 | Yes, experiments is now wrapper only | Done | Root tool is canonical; experiments path loads root module. | Low | Customer parity and experiments pytest |
| `tools/compare_questionnaire_parity.py` | `experiments/ai_crm_next/tools/compare_questionnaire_parity.py` | 160/12 | Yes, experiments is now wrapper only | Done | Root tool is canonical; experiments path loads root module. | Medium | Questionnaire parity and D7.2 tests |
| `tools/compare_user_ops_parity.py` | `experiments/ai_crm_next/tools/compare_user_ops_parity.py` | 175/12 | Yes, experiments is now wrapper only | Done | Root tool is canonical; experiments path loads root module. | Medium | User Ops parity and experiments pytest |
| `tools/automation_readonly_gray_smoke.py` | `experiments/ai_crm_next/tools/automation_readonly_gray_smoke.py` | 510/12 | Yes, experiments is now wrapper only | Done | Source-text assertions were moved to runtime side-effect checks. | Medium | Automation smoke, legacy D6 tests, experiments pytest |
| `tools/customer_read_model_gray_smoke.py` | `experiments/ai_crm_next/tools/customer_read_model_gray_smoke.py` | 467/12 | Yes, experiments is now wrapper only | Done | Source-text assertions were moved to runtime side-effect checks. | Low | Customer smoke and experiments pytest |
| `tools/product_management_gray_smoke.py` | `experiments/ai_crm_next/tools/product_management_gray_smoke.py` | 444/12 | Yes, experiments is now wrapper only | Done | Source-text assertions were moved to runtime payment/checkout safety checks. | Medium to high | Product smoke, D7.4 tests, legacy D2 tests |
| `tools/questionnaire_readonly_gray_smoke.py` | `experiments/ai_crm_next/tools/questionnaire_readonly_gray_smoke.py` | 673/12 | Yes, experiments is now wrapper only | Done | Source-text assertions were moved to runtime submit/OAuth/external safety checks. | Medium | Questionnaire smoke, legacy D5 tests |
| `tools/user_ops_readonly_gray_smoke.py` | `experiments/ai_crm_next/tools/user_ops_readonly_gray_smoke.py` | 420/12 | Yes, experiments is now wrapper only | Done | Source-text assertions were moved to runtime User Ops write/external safety checks. | Medium | User Ops smoke, legacy D4 tests |

### Experiments-Only Tools

`tools/compare_media_library_parity.py` and
`tools/media_library_gray_smoke.py` were added as root canonical tools in Phase
2B by moving the former experiments-only implementations. The experiments media
paths now use the same thin wrapper pattern as the other parity/smoke tools.

### Wrapper Feasibility

Wrapperization is feasible, but it should be phased because tests currently use
experiments tools as real import targets. Some tests monkeypatch module-level
functions, and several legacy retirement tests read experiments tool source text
to verify safety tokens. A thin wrapper that simply imports root code could make
those assertions misleading or brittle.

Recommended follow-up sequence:

1. Convert one low-risk readonly parity tool first, preferably customer read
   model parity.
2. Replace source-text safety assertions with runtime assertions that inspect
   reported side-effect flags and blocked-operation markers.
3. If wrappers are used, preserve module-level monkeypatch behavior explicitly.
4. Run root D7 focused tests, the canonical root suite, experiments pytest, and
   the six parity/smoke commands before expanding to write-adjacent capabilities.

## Guardrails Confirmed For This Assessment

- No duplicate Next source is restored.
- No D7 adapter boundary code is deleted.
- No legacy fallback is deleted or modified.
- No D7 blocker is removed.
- No production/deploy/nginx/systemd runtime configuration is modified.
- No real external call or write endpoint is executed by this assessment.

## Verification Plan

Required verification for this assessment branch:

```bash
bash scripts/check_no_duplicate_next_source.sh
scripts/run_tests.sh
cd experiments/ai_crm_next && .venv/bin/python -m pytest -q
```
