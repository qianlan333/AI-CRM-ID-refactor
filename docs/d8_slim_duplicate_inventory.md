# D8 Slim Duplicate Inventory

Date: 2026-05-21

Scope: D8 duplicate/excess inventory only. This report starts from the main branch after PR #510 and does not restore the older stacked D8 branch, does not start D9, does not remove the legacy Flask shell, and does not delete fallback code.

## Executive Summary

Current main does not contain the previously proposed D8 planning/checker/test package. The requested D8 docs, D8 checkers, D8 tests, `legacy_flask/` archive package, and lockdown shim files are not present on this branch. Because those files are absent, there are no current-main D8 docs/checkers/tests to delete or consolidate.

The only in-repo D8-adjacent runtime files in scope are existing fallback entry points and compatibility modules. They are intentionally kept:

- `app.py` remains the default AI-CRM Next runtime entry with explicit legacy fallback commands.
- `legacy_flask_app.py` remains the explicit legacy Flask fallback runner.
- `wecom_ability_service/__init__.py`, `wecom_ability_service/routes.py`, and `wecom_ability_service/http/__init__.py` remain legacy fallback surfaces.
- `openclaw_service/` remains a protected legacy external fallback surface.

No files were deleted in this inventory pass.

## Source Of Truth

| Topic | Current source of truth | Notes |
| --- | --- | --- |
| Default runtime | `app.py` and root `aicrm_next/` | AI-CRM Next stays the default runtime. |
| Legacy fallback runner | `legacy_flask_app.py` | Explicit fallback only; not removed in D8 inventory. |
| Legacy Flask app factory | `wecom_ability_service/__init__.py` | Current main has no `legacy_flask/app_factory.py`; do not import one from old stacked branches in this pass. |
| Route/fallback lockdown runtime | Not introduced on current main | If a future D8 lockdown package is reintroduced, runtime should have one implementation owner and any shim should delegate to it. |
| Route/fallback lockdown docs | Not introduced on current main | If reintroduced, use one matrix document and check it against runtime lockdown data. |
| D8 checker common logic | Not introduced on current main | If D8 checkers return, shared path/text/table/report helpers are a reasonable consolidate candidate. |

## Inventory

| Path | Line count | Category | Source-of-truth candidate | Duplicated elsewhere? | Decision | Reason | Risk | Verification needed |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- |
| `docs/d8_legacy_flask_shell_retirement_plan.md` | 0 | D8 docs | None on current main | No current-main file | needs_manual_review | Requested path is absent; do not restore from old stacked branch for this inventory pass. | Reintroducing it could duplicate runtime/fallback status already covered by existing legacy docs. | If reintroduced, compare with blocker matrices and runtime switch docs. |
| `docs/d8_legacy_shell_dependency_inventory.md` | 0 | D8 docs | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could duplicate dependency inventory if restored wholesale. | If reintroduced, verify unique ownership and references. |
| `docs/d8_legacy_shell_allowed_fallback_matrix.md` | 0 | D8 docs | Future D8 fallback docs matrix | No current-main file | needs_manual_review | Requested path is absent. | Could duplicate a future route/fallback matrix. | If reintroduced, keep a single fallback matrix source and align it with runtime data. |
| `docs/d8_1_legacy_fallback_route_lockdown_plan.md` | 0 | D8 docs | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could re-open old D8 planning before D8 scope is approved. | If reintroduced, assert planning-only status and no fallback deletion. |
| `docs/d8_1_legacy_fallback_route_matrix.md` | 0 | D8 docs | Future D8 docs matrix | No current-main file | needs_manual_review | Requested path is absent. | Could conflict with an allowed fallback matrix if both are restored. | If reintroduced, checker should compare docs matrix and runtime lockdown data. |
| `docs/d8_2_legacy_fallback_route_lockdown_enforcement.md` | 0 | D8 docs | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Enforcement docs could overstate runtime behavior if restored alone. | If reintroduced, require tests that prove enforcement is guard-only. |
| `docs/d8_2_legacy_fallback_route_lockdown_report.md` | 0 | D8 docs | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Historical report could be mistaken for current state. | If reintroduced, mark historical status clearly. |
| `docs/d8_3_legacy_flask_shell_archive_package_plan.md` | 0 | D8 docs | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could imply archive package migration has started. | If reintroduced, keep as plan only. |
| `docs/d8_3_legacy_package_move_map.md` | 0 | D8 docs | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Move maps become stale quickly if package move is not active. | If reintroduced, verify every row against live imports. |
| `docs/d8_3_legacy_import_rewrite_plan.md` | 0 | D8 docs | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could encourage import rewrites before approval. | If reintroduced, keep blocked until D8 move work is explicitly approved. |
| `docs/d8_4_legacy_flask_archive_package_implementation.md` | 0 | D8 docs | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could look like implementation is already on main. | If reintroduced, require source and test evidence. |
| `docs/d8_4_legacy_flask_archive_package_report.md` | 0 | D8 docs | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could duplicate implementation report content. | If reintroduced, shorten or consolidate with one D8 status report. |
| `docs/d8_5_legacy_db_maintenance_command_inventory.md` | 0 | D8 docs | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could overlap `app.py` command inventory. | If reintroduced, compare with actual parser commands. |
| `docs/d8_5_legacy_db_maintenance_command_retirement_plan.md` | 0 | D8 docs | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could imply retirement before fallback approval. | If reintroduced, keep commands blocked unless explicit replacement exists. |
| `docs/d8_5_maintenance_command_replacement_matrix.md` | 0 | D8 docs | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could duplicate command retirement plan rows. | If reintroduced, keep one command matrix source. |
| `tools/check_d8_legacy_shell_retirement_readiness.py` | 0 | D8 checker | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Restoring many one-off checkers may duplicate path/read/report boilerplate. | If reintroduced, consider `tools/d8_check_common.py` for mechanical helpers. |
| `tools/check_d8_1_legacy_fallback_route_lockdown.py` | 0 | D8 checker | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could duplicate route/fallback matrix parsing. | If reintroduced, share markdown table parsing and forbidden marker scan helpers. |
| `tools/check_d8_2_legacy_lockdown_enforcement.py` | 0 | D8 checker | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could duplicate enforcement/report boilerplate. | If reintroduced, keep capability-specific assertions local. |
| `tools/check_d8_3_legacy_archive_move_readiness.py` | 0 | D8 checker | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Import rewrite checks can become broad and fragile. | If reintroduced, verify against real imports with focused rules. |
| `tools/check_d8_4_legacy_archive_package.py` | 0 | D8 checker | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could confuse archive owner with compatibility shims. | If reintroduced, explicitly protect shims and fallback. |
| `tools/check_d8_5_legacy_maintenance_command_readiness.py` | 0 | D8 checker | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could duplicate parser command scans. | If reintroduced, share parser command extraction helper. |
| `tests/test_d8_legacy_shell_retirement_readiness.py` | 0 | D8 test | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Test could duplicate protected fallback existence assertions. | If reintroduced, use common expected protected files list. |
| `tests/test_d8_1_legacy_fallback_route_lockdown.py` | 0 | D8 test | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could duplicate docs/runtime matrix assertions. | If reintroduced, test one declared source of truth. |
| `tests/test_d8_2_legacy_lockdown_enforcement.py` | 0 | D8 test | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could duplicate checker subprocess setup. | If reintroduced, share lightweight test helpers only. |
| `tests/test_d8_3_legacy_archive_move_readiness.py` | 0 | D8 test | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could overconstrain import paths before archive work starts. | If reintroduced, keep as readiness-only. |
| `tests/test_d8_4_legacy_archive_package.py` | 0 | D8 test | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could force package layout not present on current main. | If reintroduced, protect both archive owner and shim relationships. |
| `tests/test_d8_5_legacy_maintenance_command_readiness.py` | 0 | D8 test | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could duplicate CLI parser assertions. | If reintroduced, keep parser expectations centralized. |
| `legacy_flask/` | 0 | D8 archive package | Future archive owner if D8 archive work is approved | No current-main directory | needs_manual_review | Requested archive package is absent on current main; do not restore it from old stacked branches in this inventory pass. | Restoring it would start D8 archive package work. | If introduced later, mark archive owner as keep and verify shims delegate to it. |
| `wecom_ability_service/__init__.py` | 216 | Compatibility/current legacy app factory | Current legacy Flask app factory | Not a duplicate | keep | Existing fallback app factory and route-owner header owner. | High; deleting or moving would affect fallback startup. | `legacy_flask_app.py --help`, fallback import smoke, root tests. |
| `wecom_ability_service/routes.py` | 13 | Compatibility/current registrar | Current legacy route blueprint export | Not a duplicate | keep | Existing compatibility route module. | High; deleting can break legacy app creation. | Root tests and legacy fallback import. |
| `wecom_ability_service/legacy_lockdown.py` | 0 | Compatibility shim | Future shim only if D8 lockdown returns | No current-main file | needs_manual_review | Requested shim is absent on current main. | Restoring a shim without runtime owner would create confusion. | If introduced later, verify it delegates to one runtime source. |
| `wecom_ability_service/http/__init__.py` | 280 | Legacy HTTP fallback registrar | Current legacy HTTP fallback surface | Not a duplicate | keep | Existing fallback route registration surface. | High; deleting would remove protected fallback. | Legacy route/fallback tests and full suite. |
| `legacy_flask_app.py` | 70 | Legacy fallback runner | Explicit fallback CLI | Not a duplicate | keep | Required legacy fallback runner. | High; deleting would remove explicit fallback command. | `python3 legacy_flask_app.py --help` and import smoke. |
| `app.py` | 138 | Runtime entry | Default Next runtime plus explicit fallback commands | Not a duplicate | keep | Canonical runtime entry; default is AI-CRM Next. | High; deleting or changing would alter runtime behavior. | `python3 app.py --help`, root full suite. |
| `openclaw_service/` | 22 | Protected external fallback | Legacy OpenClaw fallback surface | Not a duplicate | keep | Protected external fallback remains blocked. | High; deleting would remove protected fallback. | Full suite and D7/D8 blocker checks. |

## Duplicate And Excess Assessment

| Candidate | Current finding | Decision |
| --- | --- | --- |
| D8 docs | No `docs/d8_*.md` files existed before this inventory report. | Do not restore old stacked-branch docs; future D8 docs should use one status/report source and one route/fallback matrix source. |
| D8 checkers | No `tools/check_d8_*.py` files exist on current main. | If restored later, extract only mechanical helpers such as path resolution, text read, table parsing, readiness marker scans, and report writing. |
| D8 tests | No `tests/test_d8_*.py` files exist on current main before this guard test. | Keep the new guard narrow; do not recreate old D8 test stacks. |
| Archive package and shim | `legacy_flask/` and `wecom_ability_service/legacy_lockdown.py` are absent. Existing `wecom_ability_service` remains the current fallback owner. | Do not introduce archive package/shim in this inventory PR. |
| Route/fallback matrix | D8 route/fallback matrix docs and runtime lockdown implementation are absent. | Future D8 should declare exactly one runtime owner and one docs matrix, with a checker aligning them. |

## Closeout Decision

No small safe delete is available because the duplicate/excess D8 files are not present on current main. The safe action is to preserve this inventory and guard against accidental restoration of old stacked D8 material without a fresh review.
