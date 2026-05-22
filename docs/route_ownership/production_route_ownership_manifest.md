# Production Route Ownership Manifest

Status: manifest only. This document does not change runtime behavior, narrow
`production_compat` wildcard routes, enable timers, or open real external calls.

The source of truth is
`docs/route_ownership/production_route_ownership_manifest.yaml`.

## Ownership Rules

- AI-CRM Next remains the default FastAPI modular monolith runtime.
- `production_compat` catch-all routes are documented here before any future
  narrowing work.
- Next exact routers own current exact route implementations.
- `frontend_compat` owns legacy admin page parity and must not add direct
  production SQL.
- `legacy_facade` and `production_compat` entries are fallbacks, not a signal
  that old Flask is the preferred implementation.
- Timer routes remain `scheduled_safe_mode`; this manifest does not approve
  enabling timers.
- External side-effect routes remain `real_blocked`, `guarded`, or fake adapter
  contracts. This manifest does not approve real WeCom, Payment, OAuth,
  OpenClaw, or MCP external calls.
- Fixture/local_contract/demo data is not allowed in production success paths.

## Required Fields

Each route family record includes:

- `route_pattern`
- `methods`
- `capability_owner`
- `current_runtime_owner`
- `production_behavior`
- `legacy_fallback_allowed`
- `fixture_allowed_in_production`
- `external_side_effect_risk`
- `delete_ready`
- `checker`
- `notes`

## Checker

Run:

```bash
.venv/bin/python tools/check_production_route_ownership_manifest.py \
  --output-md /tmp/production_route_ownership_manifest.md \
  --output-json /tmp/production_route_ownership_manifest.json
```

The checker imports the FastAPI app with the legacy production facade enabled
so `production_compat` routes are visible in `app.routes`. It verifies:

- required route families match current app routes or production compatibility
  routes;
- every `production_compat` catch-all has a manifest entry;
- real external side-effect routes are not marked as real production behavior;
- `/admin/customers` and `/admin/questionnaires` are production readonly facade
  paths and do not allow fixture data in production;
- `/mcp` is owned by `aicrm_next.integration_gateway` and not by
  `openclaw_service`.
