# D8.3 Legacy Shell Archive Package Plan

D8.3.0 is a planning and readiness gate for moving the legacy Flask shell into a future `legacy_flask/` archive package. This round does not move code, does not delete `wecom_ability_service/`, does not delete `openclaw_service/`, does not modify production config, and does not cut traffic.

## Goal

- Plan a future migration of the old Flask shell from `wecom_ability_service/` into a clearly named archive and fallback package.
- Keep `wecom_ability_service/` in place for this round.
- Keep `legacy_flask_app.py` as the explicit fallback entrypoint.
- Keep `python3 app.py run` as AI-CRM Next.
- Keep legacy fallback usable under the D8.2 lockdown guard.
- Avoid any physical move, import rewrite, production config change, traffic cutover, external call, or old write execution.

Current D8.3 status:

| item | state |
| --- | --- |
| `legacy_shell_archive_move_status` | `planning_ready` |
| `legacy_shell_moved` | false |
| `legacy_shell_deleted` | false |
| `production_config_modified` | false |
| `production_cutover_executed` | false |
| deletion readiness | false |

## Target Future Structure

Future implementation may introduce:

```text
legacy_flask/
  __init__.py
  app_factory.py
  routes.py
  http/
  domains/
  templates/
  static/
  openclaw_legacy/
  README.md
```

`legacy_flask/` would be an archive and emergency fallback package. It would not be the default runtime, would not own retired readonly routes, and would only support explicitly allowed fallback and operational reference paths.

## Proposed Mapping

| current path | future path | note |
| --- | --- | --- |
| `wecom_ability_service/__init__.py` | `legacy_flask/app_factory.py` | legacy Flask app factory and D8.2 lockdown registration |
| `wecom_ability_service/routes.py` | `legacy_flask/routes.py` | legacy HTTP registrar |
| `wecom_ability_service/http/` | `legacy_flask/http/` | retained fallback HTTP modules |
| `wecom_ability_service/domains/` | `legacy_flask/domains/` | retained fallback services and repositories |
| `wecom_ability_service/templates/` | `legacy_flask/templates/` | retained fallback templates |
| `wecom_ability_service/static/` | `legacy_flask/static/` | retained fallback static assets |
| `wecom_ability_service/legacy_lockdown.py` | `legacy_flask/legacy_lockdown.py` | legacy-only retired route guard |
| `openclaw_service/` | keep independent until D9, or later `legacy_flask/openclaw_legacy/` | D7.7 keeps OpenClaw legacy bridge as retained fallback/reference |

`openclaw_service/` is not moved in D8.3 because OpenClaw legacy adapter retirement remains a separate gate with its own compatibility, rollback, and signoff requirements.

## Import Strategy

Future implementation should:

- Change `legacy_flask_app.py` to import the app factory from `legacy_flask.app_factory`.
- Keep a temporary `wecom_ability_service` compatibility shim during the rollback window.
- Keep the shim limited to import compatibility; it must not add new business behavior.
- Keep `python3 app.py run` on `aicrm_next.main:app`.
- Keep `python3 app.py run-legacy` routed through the shim or new archive package only after smoke evidence exists.
- Rewrite `from wecom_ability_service.*` imports to `from legacy_flask.*` only inside legacy fallback surfaces, tests, and tools that explicitly exercise legacy fallback.
- Never introduce legacy imports into `aicrm_next`.

## Phases

| phase | scope | status in this round |
| --- | --- | --- |
| D8.3.0 planning only | plan, move map, import rewrite strategy, checker, tests | complete candidate |
| D8.3.1 create archive package skeleton | add empty package and README only | future |
| D8.3.2 move app factory and HTTP registrar | move app factory/routes with shim | future |
| D8.3.3 move domains/templates/static | move retained fallback implementation files | future |
| D8.3.4 add temporary `wecom_ability_service` shim | compatibility exports for rollback window | future |
| D8.3.5 remove shim after operational window | only after evidence and signoff | future |

D8.3.0 is the only phase completed by this round.

## Move Gates

Implementation must not begin until all of the following are true:

- D8.2 lockdown enforcement is accepted.
- `python3 app.py --help`, `python3 legacy_flask_app.py --help`, and legacy fallback import smoke pass.
- Default AI-CRM Next has no runtime import of legacy shell packages.
- D8.2 lockdown checker passes.
- Deploy, systemd, cron, runbook, tests, and tooling references are audited.
- Import rewrite map is complete.
- Rollback plan is approved.
- Human signoff is recorded.

## Rollback

- Any future move implementation must be revertible with `git revert`.
- The temporary shim must stay through an agreed rollback window.
- `run-legacy` smoke must pass before and after each move phase.
- Production config must remain unchanged during move implementation.
- If import rewrite breaks fallback, revert to the old package path and rerun D8.2 lockdown checker.
