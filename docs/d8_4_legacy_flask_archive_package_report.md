# D8.4 Legacy Flask Archive Package Report

## Summary

D8.4 creates the `legacy_flask/` archive package and moves the legacy Flask shell entry layer there. The default runtime remains AI-CRM Next, and explicit legacy fallback remains available.

## Changed Runtime Entry Layer

- `legacy_flask.app_factory.create_app` is the legacy app factory entrypoint.
- `legacy_flask_app.py` imports the app factory from `legacy_flask.app_factory`.
- `app.py run-legacy` imports the app factory from `legacy_flask.app_factory`.
- `wecom_ability_service.create_app` remains available through a compatibility shim.

## Compatibility Shims

The shim files retain old import compatibility:

- `wecom_ability_service/__init__.py`
- `wecom_ability_service/routes.py`
- `wecom_ability_service/http/__init__.py`
- `wecom_ability_service/legacy_lockdown.py`

Each shim contains `LEGACY_COMPATIBILITY_SHIM` and forwards to `legacy_flask.*`.

## Files Not Moved

`wecom_ability_service/domains/`, `wecom_ability_service/templates/`, `wecom_ability_service/static/`, and most legacy HTTP modules remain in place. They are still legacy fallback dependencies and will need separate move or retirement gates.

`openclaw_service/` remains retained and pending D9.

## Verification Expectations

- D8.4 checker passes.
- D8.4 targeted tests pass.
- `python3 app.py --help` passes.
- `python3 legacy_flask_app.py --help` passes.
- `from legacy_flask.app_factory import create_app` passes.
- `from wecom_ability_service import create_app` passes.
- D8.2 lockdown checker still passes.

## Safety

D8.4 does not modify production config, does not cut traffic, does not call external services, and does not execute old write endpoints.
