# Legacy Facade Growth Freeze Policy

Status: Phase 1 guardrail only. This policy does not switch production runtime,
delete legacy Flask, enable real external calls, or change deploy/systemd/nginx
configuration.

## Positioning

`legacy_flask_facade` and `production_compat` are compatibility boundaries for
production compatibility, hotfixes, rollback, and external side effects that do
not yet have a safe AI-CRM Next adapter. They are not default implementation
paths for new features.

New product work defaults to AI-CRM Next native modules under the modular
monolith. A legacy facade route may only preserve existing behavior while the
replacement owner is explicit and guarded.

## Allowed Exceptions

Adding a legacy facade or `production_compat` route requires all of these:

- It is a production hotfix, a rollback compatibility path, or a route whose
  real external side effect does not yet have a Next adapter.
- Production data is still stably served only by the legacy service.
- `docs/route_ownership/production_route_ownership_manifest.yaml` is updated in
  the same change.
- The route entry names the replacement owner, delete condition, and checker in
  notes or an adjacent route-ownership document.
- The route keeps `fixture_allowed_in_production: false` and does not mark real
  external calls as allowed.

## Forbidden

- Do not add direct `wecom_ability_service` or `openclaw_service` imports inside
  `aicrm_next`.
- Do not use `importlib` or string concatenation outside
  `aicrm_next/integration_gateway/legacy_flask_facade.py` to bypass import
  checks for `wecom_ability_service`.
- Do not modify `production_compat` wildcard coverage without updating the route
  ownership manifest and checker.
- Do not add direct SQL in `aicrm_next/frontend_compat`.
- Do not treat fixture, local_contract, or demo data as production success data.

## Replacement Order

1. Replace read-only routes first.
2. Replace internal write routes second.
3. Replace external side-effect routes third.
4. Replace timer and automation execution routes last.

## Checker

Run:

```bash
python3 tools/check_legacy_facade_growth_freeze.py \
  --output-md /tmp/legacy_facade_growth_freeze.md \
  --output-json /tmp/legacy_facade_growth_freeze.json
```

The checker is static and deterministic. It enforces the legacy import boundary,
blocks direct SQL in `frontend_compat`, verifies this policy and route ownership
documents exist, and rejects manifest entries that allow production fixtures or
real external side effects.

## Replacement Backlog

Phase 2 backlog is the planning source for gradually replacing legacy facade and
`production_compat` route families. Before any route family replacement starts,
the backlog entry must name `replacement_owner`, `delete_condition`, and
`rollback_path`.

The backlog does not authorize runtime switching, fallback deletion, or real
external calls. For routes with `daily_business_critical: true`, replacement
work must use gray release, parity checks, and fallback retention so current
daily business usage is not interrupted.
