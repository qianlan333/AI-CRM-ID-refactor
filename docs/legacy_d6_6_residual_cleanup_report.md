# Legacy D6.6 Residual Cleanup Report

## Scope

D6.6 runs after D6.5, #498, and #499. The goal is residual cleanup only:

- keep root `aicrm_next/` as the only AI-CRM Next production source
- keep `experiments/ai_crm_next/` as docs, tools, tests, fixtures, migrations, scripts, and metadata
- clean stale wording that can be misread as current D1-D6 route state
- leave D7 write, external, runtime, payment, OAuth, WeCom, OpenClaw, archive, contacts, identity, MCP, deploy, and fallback files untouched

## Baseline

This branch started from latest `origin/main` at the #499 merge commit. Baseline checks passed before cleanup:

- D6.5 dead cleanup checker passed.
- Next-source, dead-cleanup, and delete-batch status tests passed.
- `scripts/run_tests.sh` passed.
- experiments pytest passed after creating the ignored local `.venv`.

## Residual Reference Scan

| scan | result | decision |
| --- | --- | --- |
| `rg "experiments/ai_crm_next/src/aicrm_next|src/aicrm_next|PYTHONPATH=src|pythonpath = [\"src\"]|from src.aicrm_next|src layout|duplicate Next source|experiments package source"` | Active code/config references are absent. Remaining duplicate-source path mentions are the historical #498 report, the D6.5/D6.6 inventory row, the experiment README guard wording, and tests that prevent the duplicate package from returning. | keep historical references and guard them as non-active import/config paths |
| `find experiments/ai_crm_next -path '*/src/aicrm_next*' -print` | no files found | no duplicate source restored |
| `rg` for D1-D6 stale status wording, canary/signoff wording, and deleted route-inventory references | Current-state stale wording was found in `docs/legacy_retirement_plan.md`; experiment canary docs contain historical signoff vocabulary; deleted route-inventory mentions are historical D6.5 evidence. | update current-state stale wording and add historical notes where the file name does not trigger production-config safety guards |
| `rg "image_library_endpoint|image_library_create|attachment_library_endpoint|miniprogram_library_endpoint|admin_wechat_pay_products|customer_center.py|customer_timeline.py|admin_user_ops.py|admin_user_ops_delivery.py|attachment_library.html|docs/generated/route_inventory"` | References are tests, checkers, historical retirement docs, archived refactor docs, or D7 matrix context. No runtime registrar import for deleted readonly owners was found. | no additional file deletion |
| `find wecom_ability_service/templates -type f` plus template render scans | remaining templates are rendered by root `aicrm_next/frontend_compat`, legacy write/external fallback routes, or tests/docs. | no template deletion |

## Changes

- Clarified `docs/legacy_retirement_plan.md` so it no longer carries pre-D4 stale wording after D4-D6 have completed.
- Marked duplicate-source path mentions in `docs/next_source_consolidation_report.md` as historical deletion evidence only.
- Added historical notes to experiment canary docs so their readiness vocabulary is not mistaken for current route ownership.
- Updated `docs/legacy_dead_code_inventory.md` with the D6.6 residual scan result.
- Extended regression tests to keep duplicate-source references non-active and current D1-D6.5 docs aligned.

## Deleted Files

None.

No D7 blocker/fallback file was deleted. The scan found no additional D1-D6 readonly leftover that satisfied all deletion conditions.
