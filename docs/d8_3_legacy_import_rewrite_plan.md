# D8.3 Legacy Import Rewrite Plan

D8.3.0 documents the future import rewrite strategy only. It does not rewrite imports, create `legacy_flask/`, move code, delete code, or change production config.

## Current Import Graph Summary

- `app.py` defaults to AI-CRM Next and only reaches legacy Flask through explicit fallback commands.
- `legacy_flask_app.py` imports the legacy Flask app factory from `legacy_flask.app_factory`.
- `wecom_ability_service/__init__.py` is now a compatibility shim for the archive app factory.
- Legacy HTTP modules import from `wecom_ability_service.domains`, templates, static assets, and helper packages.
- `openclaw_service/` remains an independent legacy adapter fallback/reference surface.
- `aicrm_next` must not import `wecom_ability_service`, `openclaw_service`, or the `legacy_flask` archive package.

## Rewrite Strategy Status

D8.4 rewrites the shell entry layer. Remaining future implementation should rewrite legacy-only imports from:

```text
from wecom_ability_service...
import wecom_ability_service...
```

to:

```text
from legacy_flask...
import legacy_flask...
```

Only legacy fallback code, legacy tests, and legacy diagnostics should be rewritten. AI-CRM Next runtime code must stay independent.

## Temporary Shim Strategy

`wecom_ability_service` may become a temporary compatibility shim after the move. The shim should:

- Export the moved app factory and any required legacy compatibility names.
- Keep `python3 app.py run-legacy` and `python3 legacy_flask_app.py run` working during the rollback window.
- Avoid new business logic.
- Avoid real external calls.
- Emit clear comments or docs pointing to `legacy_flask/`.

The shim exists only for compatibility and rollback, not for new development.

## Files Requiring Manual Rewrite

- `legacy_flask_app.py`
- `wecom_ability_service/__init__.py` after it becomes a shim
- legacy HTTP modules under `wecom_ability_service/http/`
- legacy domain modules under `wecom_ability_service/domains/`
- fallback tests that import legacy app factory or legacy helpers
- fallback tools and checkers that import `wecom_ability_service`
- docs that describe fallback package paths

## Files Not To Rewrite Yet

- `app.py` default AI-CRM Next import.
- `aicrm_next/**`.
- Production deploy, nginx, systemd, cron, or process-manager config.
- `openclaw_service/**` until D9 or a later accepted OpenClaw archive gate.
- Any old write/external fallback path before its own route and rollback evidence exists.

## Required Tests After Rewrite

- `python3 app.py --help`
- `python3 legacy_flask_app.py --help`
- `python3 -c "from legacy_flask_app import main"`
- D8.2 lockdown checker.
- Legacy retired route smoke.
- Allowed fallback diagnostic smoke.
- Focused import scan proving `aicrm_next` has no legacy imports.
- Targeted tests for the move phase.

## Rollback Strategy

- Use `git revert` for each move phase.
- Keep `wecom_ability_service` shim until the agreed rollback window closes.
- Do not alter production config during move implementation.
- If fallback import, route lockdown, or smoke checks fail, revert to the old package path and rerun D8.2 checker.
