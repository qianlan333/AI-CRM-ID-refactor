# D8 Slim Duplicate Inventory

Date: 2026-05-21

Scope: D8 duplicate/excess inventory only. This report starts from the main branch after PR #510 and does not restore the older stacked D8 branch, does not start D9, does not remove the legacy Flask shell, and does not delete fallback code.

## Executive Summary

Current main now contains only the minimal D8.0/D8.1 planning package restarted after the #511 inventory. The older stacked D8.2-D8.5 package is still absent and must not be restored without a fresh review.

The only in-repo D8-adjacent runtime files in scope are existing fallback entry points and compatibility modules. They are intentionally kept:

- `app.py` remains the default AI-CRM Next runtime entry with explicit legacy fallback commands.
- `legacy_flask_app.py` remains the explicit legacy Flask fallback runner.
- `wecom_ability_service/__init__.py`, `wecom_ability_service/routes.py`, and `wecom_ability_service/http/__init__.py` remain legacy fallback surfaces.
- `openclaw_service/` is absent after D9.6 physical deletion and must not be restored by D8 work.

No files were deleted in this inventory pass.

## Source Of Truth

| Topic | Current source of truth | Notes |
| --- | --- | --- |
| Default runtime | `app.py` and root `aicrm_next/` | AI-CRM Next stays the default runtime. |
| Legacy fallback runner | `legacy_flask_app.py` | Explicit fallback only; not removed in D8 inventory. |
| Legacy Flask app factory | `wecom_ability_service/__init__.py` | Current main has no `legacy_flask/app_factory.py`; do not import one from old stacked branches in this pass. |
| Route/fallback lockdown runtime | Not introduced on current main | D8.1 is planning-only; no runtime guard or shim exists. |
| Route/fallback lockdown docs | `docs/d8_1_legacy_fallback_route_matrix.md` | D8.1 docs matrix is planning-only and is checked by `tools/check_d8_1_legacy_fallback_route_lockdown.py`. |
| D8 checker common logic | Not introduced on current main | Minimal D8.0/D8.1 checkers are small; shared helper extraction can wait until more D8 phases are approved. |

## Inventory

| Path | Line count | Category | Source-of-truth candidate | Duplicated elsewhere? | Decision | Reason | Risk | Verification needed |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- |
| `docs/d8_legacy_flask_shell_retirement_plan.md` | 65 | D8 docs | D8.0 shell retirement plan | Not duplicated | keep | Minimal planning/readiness-only plan restarted from current main. | Low; docs-only, no runtime behavior. | D8.0 checker and targeted tests. |
| `docs/d8_legacy_shell_dependency_inventory.md` | 29 | D8 docs | D8.0 dependency inventory | Not duplicated | keep | Documents current dependency ownership without moving app factory. | Low; docs-only. | D8.0 checker and targeted tests. |
| `docs/d8_legacy_shell_allowed_fallback_matrix.md` | 22 | D8 docs | D8.0 allowed fallback matrix | Not duplicated | keep | Documents allowed fallback categories while planning remains blocked. | Low; docs-only. | D8.0 checker and targeted tests. |
| `docs/d8_1_legacy_fallback_route_lockdown_plan.md` | 34 | D8 docs | D8.1 planning plan | Not duplicated | keep | Planning-only route/fallback lockdown plan with no runtime enforcement. | Low; docs-only. | D8.1 checker and targeted tests. |
| `docs/d8_1_legacy_fallback_route_matrix.md` | 19 | D8 docs | D8.1 docs matrix | Not duplicated | keep | Single planning matrix for future route/fallback lockdown candidates. | Low; docs-only. | D8.1 checker and targeted tests. |
| `docs/d8_2_legacy_fallback_route_lockdown_preflight.md` | 52 | D8 docs | D8.2 preflight report | Not duplicated | keep | Preflight-only status check; does not register runtime enforcement. | Low; docs-only. | D8.2 preflight checker and targeted tests. |
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
| `tools/check_d8_legacy_shell_retirement_readiness.py` | 151 | D8 checker | D8.0 planning checker | Not duplicated | keep | Small planning/readiness checker for docs, gates, protected files, and absent runtime package. | Low; checker-only. | Targeted D8.0 tests and full suite. |
| `tools/check_d8_1_legacy_fallback_route_lockdown.py` | 136 | D8 checker | D8.1 planning checker | Not duplicated | keep | Small planning checker for matrix categories and no runtime enforcement. | Low; checker-only. | Targeted D8.1 tests and full suite. |
| `tools/check_d8_2_legacy_lockdown_preflight.py` | 244 | D8 checker | D8.2 preflight checker | Not duplicated | keep | Preflight checker confirms D8.0/D8.1 prerequisites, absent runtime guard/package, and not-ready blockers. | Low; checker-only. | Targeted D8.2 tests and full suite. |
| `tools/check_d8_2_legacy_lockdown_enforcement.py` | 0 | D8 checker | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could duplicate enforcement/report boilerplate. | If reintroduced, keep capability-specific assertions local. |
| `tools/check_d8_3_legacy_archive_move_readiness.py` | 0 | D8 checker | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Import rewrite checks can become broad and fragile. | If reintroduced, verify against real imports with focused rules. |
| `tools/check_d8_4_legacy_archive_package.py` | 0 | D8 checker | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could confuse archive owner with compatibility shims. | If reintroduced, explicitly protect shims and fallback. |
| `tools/check_d8_5_legacy_maintenance_command_readiness.py` | 0 | D8 checker | None on current main | No current-main file | needs_manual_review | Requested path is absent. | Could duplicate parser command scans. | If reintroduced, share parser command extraction helper. |
| `tests/test_d8_legacy_shell_retirement_readiness.py` | 94 | D8 test | D8.0 planning test | Not duplicated | keep | Guards planning-only status, gate evidence, and protected fallback existence. | Low; test-only. | Full suite. |
| `tests/test_d8_1_legacy_fallback_route_lockdown.py` | 79 | D8 test | D8.1 planning test | Not duplicated | keep | Guards planning-only matrix and absence of runtime guard/package. | Low; test-only. | Full suite. |
| `tests/test_d8_2_legacy_lockdown_preflight.py` | 78 | D8 test | D8.2 preflight test | Not duplicated | keep | Guards preflight-only state and absence of runtime guard/package. | Low; test-only. | Full suite. |
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
| `openclaw_service/` | 0 | Deleted OpenClaw repo shim | D9.6 physical deletion report | No current-main directory | keep absent | Repo-side shim/archive deletion is recorded by D9.6; D8 must not restore it. | High; reintroducing it would conflict with D9.6. | D9.6 checker and status consistency tests. |

## Duplicate And Excess Assessment

| Candidate | Current finding | Decision |
| --- | --- | --- |
| D8 docs | D8.0/D8.1 planning docs and D8.2 preflight docs are present; D8.3-D8.5 docs remain absent. | Keep minimal docs; do not restore old stacked-branch docs. |
| D8 checkers | D8.0/D8.1 planning checkers and D8.2 preflight checker are present. | Keep small checker duplication acceptable; consider a helper only if more D8 checkers return. |
| D8 tests | D8.0/D8.1 planning tests, D8.2 preflight tests, and this slim inventory guard are present. | Keep tests focused; do not recreate old D8 test stacks. |
| Archive package and shim | `legacy_flask/` and `wecom_ability_service/legacy_lockdown.py` are absent. Existing `wecom_ability_service` remains the current fallback owner. | Do not introduce archive package/shim in this inventory PR. |
| Route/fallback matrix | D8 route/fallback matrix docs and runtime lockdown implementation are absent. | Future D8 should declare exactly one runtime owner and one docs matrix, with a checker aligning them. |

## Closeout Decision

No small safe delete is available. The safe action is to keep the minimal D8.0/D8.1 planning package plus D8.2 preflight, leave D8.3-D8.5 absent, and guard against accidental restoration of old stacked D8 material without a fresh review.
