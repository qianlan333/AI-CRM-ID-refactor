# D8.2 Legacy Fallback Route Lockdown Report

## Summary

D8.2 status: `lockdown_enforcement_implemented`.

The legacy Flask fallback now has a runtime guard that blocks D1-D6 retired readonly owner routes with HTTP 410 while leaving allowed fallback routes available.

## Implemented Files

- `wecom_ability_service/legacy_lockdown.py`
- `tools/check_d8_2_legacy_lockdown_enforcement.py`
- `tests/test_d8_2_legacy_lockdown_enforcement.py`

## App Factory Integration

`wecom_ability_service.create_app` imports and registers `register_legacy_lockdown(app)`.

This affects only explicit legacy fallback runtime:

- `python3 app.py run-legacy`
- `python3 legacy_flask_app.py run`

Default runtime remains AI-CRM Next:

- `python3 app.py run`

## Retired Route Evidence

Representative retired routes checked by the D8.2 checker:

- `GET /api/customers`
- `GET /admin/customers`
- `GET /api/admin/user-ops/overview`
- `GET /admin/questionnaires`
- `GET /api/admin/automation-conversion/overview`

Expected behavior: HTTP 410 and `legacy_route_retired`.

## Allowed Fallback Evidence

Representative allowed fallback route checked by the D8.2 checker:

- `GET /api/system/health`

Expected behavior: not blocked by lockdown.

Allowed fallback remains fallback only, not production ownership.

## Safety

- Legacy shell retained.
- `openclaw_service/` retained.
- Production config unchanged.
- Production traffic not cut.
- Real external adapters not enabled.
- Old write endpoints not executed by D8.2 verification.

## Next Step

D8.2 should go to acceptance review before any D8.3 archive package or later deletion planning.
