# D8 Legacy Shell Dependency Inventory

Status: planning/readiness only.

This inventory records current legacy shell dependencies on `main`. It is not a move map and does not approve package relocation.

| Dependency | Current path | Current role | D8.0 decision | Risk |
| --- | --- | --- | --- | --- |
| Runtime entry | `app.py` | Default AI-CRM Next entry plus explicit legacy fallback commands. | keep | Changing it would alter runtime behavior. |
| Legacy runner | `legacy_flask_app.py` | Explicit fallback CLI for legacy Flask. | keep | Removing it would remove rollback/fallback access. |
| Legacy app factory | `wecom_ability_service/__init__.py` | Current Flask app factory and route-owner header setup. | keep | Moving it before D8 approval would break imports and fallback startup. |
| Legacy routes export | `wecom_ability_service/routes.py` | Compatibility blueprint export. | keep | Removing it can break app factory registration. |
| Legacy HTTP registrar | `wecom_ability_service/http/__init__.py` | Registers legacy HTTP fallback routes. | keep | Removing it would remove protected fallback surfaces. |
| External fallback | D7.5/D7.7 fake OpenClaw/MCP adapter boundary | Repo-side `openclaw_service/` is absent after D9.6; real OpenClaw/MCP behavior remains blocked. | keep | Do not reintroduce the deleted repo shim; keep the fake adapter boundary until real evidence exists. |
| Next runtime source | `aicrm_next/` | Production Next source of truth. | keep | Must remain root-only; duplicate experiment source must stay absent. |

## Current Import Relationship

- `app.py run` imports `aicrm_next.main:app` through Uvicorn.
- `app.py run-legacy` imports `wecom_ability_service.create_app`.
- `legacy_flask_app.py run` imports `wecom_ability_service.create_app`.
- Current `main` has no `legacy_flask/` archive package and no `wecom_ability_service/legacy_lockdown.py` shim.

## D8.0 Decision

Keep all existing runtime and fallback dependencies in place. Any future archive package or import rewrite must be introduced by a separate D8 phase with explicit tests and rollback proof.
