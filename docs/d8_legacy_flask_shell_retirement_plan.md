# D8 Legacy Flask Shell Retirement Plan

D8.0 is a planning and readiness gate only. It does not delete the legacy Flask shell, does not remove `wecom_ability_service/`, does not remove `openclaw_service/`, does not remove `legacy_flask_app.py`, and does not change production routing.

## Current State

| item | state |
| --- | --- |
| `legacy_flask_shell_status` | `retirement_planning_ready` |
| deletion readiness | false |
| `production_cutover_executed` | false |
| `real_external_adapters_enabled` | false |

- `python3 app.py run` defaults to AI-CRM Next through `aicrm_next.main:app`.
- `python3 app.py run-legacy` and `python3 legacy_flask_app.py run` still provide explicit legacy Flask fallback.
- `legacy_flask_app.py` is retained as the fallback entrypoint.
- `wecom_ability_service/` is retained as legacy shell, fallback, and reference code.
- `openclaw_service/` is retained as legacy adapter fallback and reference code.
- D1-D6 readonly route owners have been retired or tombstoned according to their own batch evidence.
- D7.1-D7.7 adapter contracts are complete in fake or staging-disabled form.
- Real external adapters are not enabled for production behavior.
- This D8.0 plan does not execute traffic cutover, external calls, old writes, or Next production writes.

## Why Not Delete The Shell Immediately

The legacy shell remains necessary because several production or rollback gates are still incomplete:

- Real WeCom dispatch has not completed production cutover.
- Real OAuth has not completed production cutover.
- Real payment provider calls and payment notification handling have not completed production cutover.
- Real OpenClaw and MCP bridge calls have not completed production cutover.
- Real archive and contacts sync have not completed production cutover.
- Identity mapping and customer projection writes are still fake or guarded contracts, not production writes.
- Production rollback may still require the legacy Flask fallback.
- Deploy, systemd, and operational scripts may still reference legacy commands such as `python3 app.py init-db`.
- Existing tests and diagnostics still use legacy modules as reference or fallback surfaces.

## D8 Retirement Phases

| phase | goal | runtime change | deletion scope |
| --- | --- | --- | --- |
| D8.0 Planning / readiness gate | Inventory dependencies, allowed fallback, and future gate criteria | none | none |
| D8.1 Legacy fallback route lockdown planning | Define allowed fallback registry, retired readonly route matrix, and checker | none | none |
| D8.2 Legacy fallback route lockdown enforcement | Register a legacy-only guard that returns 410 for retired D1-D6 readonly routes while preserving allowed fallback | legacy fallback only | none |
| D8.3 Legacy Flask archive package plan | Plan moving the shell into a `legacy_flask/` archive package | none in D8.3.0 | none |
| D8.4 Legacy Flask archive package implementation | Create `legacy_flask/` and move the app factory, route facade, HTTP registrar facade, and lockdown entry layer | explicit legacy fallback only | none |
| D8.5 Legacy DB / maintenance command retirement planning | Inventory legacy DB init and maintenance commands, define replacement matrix, and gate future command removal | none | none |

D8.0 completed the first row. D8.1 added lockdown planning/checker evidence. D8.2 implements the legacy-only runtime guard for retired readonly routes; it still does not delete shell code, change production config, or cut traffic.

D8.0 only changed planning, readiness, checker, and test artifacts; D8.2 is the first runtime guard change, and it is scoped to explicit legacy fallback runtime only.

## Delete Gate

No legacy shell deletion may happen until all of the following are true:

- Production AI-CRM Next has handled all agreed route families for the agreed observation window.
- All D7 capabilities are either production cut over with evidence or explicitly deprecated by product and operations owners.
- Production logs show no hits to legacy Flask route owners during the observation window.
- Rollback no longer requires the legacy Flask app factory.
- Deploy and systemd use a Next-only entrypoint.
- Database migration, backfill, and maintenance command replacement are complete.
- External adapter production evidence is archived for WeCom, OAuth, Payment, OpenClaw, MCP, archive, contacts, identity, and projection behavior.
- Human signoff is recorded.
- Backup and rollback plans exist for each retirement phase.

## Rollback

- D8.0 changes no runtime behavior, so rollback is documentation/checker/test revert only.
- D8.1-D8.5 must each have a separate rollback plan and separate acceptance evidence.
- The current rollback owner remains the explicit legacy Flask fallback.
- If Next route ownership or real external adapter behavior fails in later phases, use `python3 app.py run-legacy` or `python3 legacy_flask_app.py run` only under the documented rollback procedure.

## D8.0 Acceptance Evidence

D8.0 acceptance requires:

- This plan exists and states that no shell deletion occurs.
- The dependency inventory exists and covers shell core, OpenClaw, deploy/systemd references, docs, tests, and tools.
- The allowed fallback matrix exists and separates fallback permission from production ownership.
- The D8 checker passes.
- Targeted D8 tests pass.
- `app.py` still defaults to AI-CRM Next.
- `legacy_flask_app.py`, `wecom_ability_service/`, and `openclaw_service/` still exist.
- No deploy, production, nginx, or systemd configuration is modified by D8.0.

## D8.1 Lockdown Planning Addendum

D8.1 status: `lockdown_planning_ready`.

D8.1 adds:

- `docs/d8_1_legacy_fallback_route_lockdown_plan.md`
- `docs/d8_1_legacy_fallback_route_matrix.md`
- `tools/check_d8_1_legacy_fallback_route_lockdown.py`
- `tests/test_d8_1_legacy_fallback_route_lockdown.py`

D8.1 still does not delete the legacy shell, does not modify production config, does not cut traffic, and does not execute external calls. D8.2 is the future phase for route lockdown enforcement implementation such as hard blocks, 410 responses, or denylist enforcement.

## D8.2 Lockdown Enforcement Addendum

D8.2 status: `lockdown_enforcement_implemented`.

D8.2 adds:

- `wecom_ability_service/legacy_lockdown.py`
- `docs/d8_2_legacy_fallback_route_lockdown_enforcement.md`
- `docs/d8_2_legacy_fallback_route_lockdown_report.md`
- `tools/check_d8_2_legacy_lockdown_enforcement.py`
- `tests/test_d8_2_legacy_lockdown_enforcement.py`

The D8.2 guard is registered only by the explicit legacy Flask fallback app factory. It returns a retired JSON response and route-owner headers for D1-D6 readonly routes that AI-CRM Next already owns. Allowed fallback routes for payment, OAuth, archive/contact sync, OpenClaw, questionnaire submit, operational diagnostics, and other guarded write/external recovery paths continue to pass through the legacy runtime.

D8.2 does not delete `legacy_flask_app.py`, `wecom_ability_service/`, or `openclaw_service/`. It does not modify production config, cut traffic, execute old writes, or call external services.

## D8.3 Archive Move Planning Addendum

D8.3 status: `archive_move_planning_ready`.

D8.3 adds:

- `docs/d8_3_legacy_flask_shell_archive_package_plan.md`
- `docs/d8_3_legacy_package_move_map.md`
- `docs/d8_3_legacy_import_rewrite_plan.md`
- `tools/check_d8_3_legacy_archive_move_readiness.py`
- `tests/test_d8_3_legacy_archive_move_readiness.py`

D8.3.0 is planning only. It defines the future `legacy_flask/` archive package target, move map, import rewrite strategy, shim strategy, rollback plan, and readiness checker. It does not create `legacy_flask/`, does not move `wecom_ability_service/`, does not move `openclaw_service/`, does not delete shell files, does not modify production config, and does not cut traffic.

## D8.4 Archive Package Addendum

D8.4 status: `archive_package_created`.

D8.4 adds:

- `legacy_flask/__init__.py`
- `legacy_flask/app_factory.py`
- `legacy_flask/routes.py`
- `legacy_flask/http/__init__.py`
- `legacy_flask/legacy_lockdown.py`
- `legacy_flask/README.md`
- `docs/d8_4_legacy_flask_archive_package_implementation.md`
- `docs/d8_4_legacy_flask_archive_package_report.md`
- `tools/check_d8_4_legacy_archive_package.py`
- `tests/test_d8_4_legacy_archive_package.py`

D8.4 moves the shell entry layer into `legacy_flask/` and keeps `wecom_ability_service/` as a compatibility shim and legacy module holder. It does not move `openclaw_service/`, does not move domains/templates/static, does not delete legacy fallback, does not modify production config, and does not cut traffic.

## D8.5 Maintenance Command Planning Addendum

D8.5 status: `maintenance_command_retirement_planning_ready`.

D8.5 adds:

- `docs/d8_5_legacy_db_maintenance_command_inventory.md`
- `docs/d8_5_legacy_db_maintenance_command_retirement_plan.md`
- `docs/d8_5_maintenance_command_replacement_matrix.md`
- `tools/check_d8_5_legacy_maintenance_command_readiness.py`
- `tests/test_d8_5_legacy_maintenance_command_readiness.py`

D8.5 inventories legacy DB init, schema bootstrap, cleanup, diagnostic, backfill, and rollback commands. It defines replacement paths and delete gates for future work. It does not remove legacy commands, execute production DB migration, clean production data, modify production config, or cut traffic.
