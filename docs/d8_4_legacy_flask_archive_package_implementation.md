# D8.4 Legacy Flask Archive Package Implementation

D8.4 creates the `legacy_flask/` archive package and moves the legacy shell entry layer into it. This round does not delete `wecom_ability_service/`, does not delete `openclaw_service/`, does not modify production config, and does not cut traffic.

## Scope

- Create `legacy_flask/`.
- Move the legacy app factory entry layer to `legacy_flask/app_factory.py`.
- Move the route facade to `legacy_flask/routes.py`.
- Move the HTTP registrar facade to `legacy_flask/http/__init__.py`.
- Move the D8.2 retired-route lockdown guard to `legacy_flask/legacy_lockdown.py`.
- Keep `wecom_ability_service/` as a compatibility shim and legacy module holder.
- Keep most domains, templates, and static assets in the old location for this slice.
- Update `legacy_flask_app.py` and explicit legacy commands in `app.py` to use `legacy_flask.app_factory`.

## Created Archive Package

`legacy_flask/` contains:

- `__init__.py`
- `app_factory.py`
- `routes.py`
- `http/__init__.py`
- `legacy_lockdown.py`
- `README.md`

The package is an archive and fallback package. It is not the default runtime and does not own retired readonly routes.

## Compatibility Shim Strategy

The following files remain and expose compatibility shims:

- `wecom_ability_service/__init__.py`
- `wecom_ability_service/routes.py`
- `wecom_ability_service/http/__init__.py`
- `wecom_ability_service/legacy_lockdown.py`

Each shim is marked with `LEGACY_COMPATIBILITY_SHIM`. The shim forwards old imports to `legacy_flask.*` without adding business logic.

## Files Moved / Files Not Moved

Moved into `legacy_flask/`:

- app factory entry layer
- route facade
- HTTP registrar facade
- lockdown guard

Not moved in this round:

- `wecom_ability_service/domains/`
- `wecom_ability_service/templates/`
- `wecom_ability_service/static/`
- most legacy HTTP controller modules
- `openclaw_service/`

These remain in place because the goal is to archive the shell entry layer first while preserving fallback behavior and rollback. Moving domains/templates/static requires a separate loader/import rewrite pass and broader smoke evidence.

## Runtime Behavior

- `python3 app.py run` remains AI-CRM Next.
- `python3 app.py run-legacy` uses `legacy_flask.app_factory`.
- `python3 legacy_flask_app.py run` uses `legacy_flask.app_factory`.
- `from wecom_ability_service import create_app` still works through the shim.

## Lockdown Regression

D8.2 lockdown remains active from `legacy_flask.legacy_lockdown`.

- retired readonly legacy routes return 410 with `legacy_route_retired`
- allowed fallback diagnostic routes are not blocked

## Rollback

Rollback is a revert of D8.4. Because `wecom_ability_service/` remains in place and shims keep old imports working, rollback does not require production config changes or traffic changes.

## Non-Goals

- No deletion of `wecom_ability_service/`.
- No deletion of `openclaw_service/`.
- No production/deploy/nginx/systemd changes.
- No traffic cutover.
- No real external calls.
- No old write endpoint execution.
