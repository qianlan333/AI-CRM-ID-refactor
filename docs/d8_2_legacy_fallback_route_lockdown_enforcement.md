# D8.2 Legacy Fallback Route Lockdown Enforcement

D8.2 implements runtime lockdown enforcement inside the explicit legacy Flask fallback only. It does not delete the legacy shell, does not modify production config, and does not cut traffic.

## Scope

- Add `wecom_ability_service/legacy_lockdown.py`.
- Register `register_legacy_lockdown(app)` in the legacy Flask app factory.
- Return a stable retired response for D1-D6 readonly owner routes.
- Keep allowed fallback routes available.
- Keep `python3 app.py run` unchanged as AI-CRM Next.

## Runtime Guard Design

The guard is a Flask `before_request` handler registered by `wecom_ability_service.create_app`.

Evaluation order:

1. Match allowed fallback routes first.
2. If no allowed fallback matches, match retired readonly routes.
3. Retired readonly routes return HTTP 410.
4. Non-matching routes continue through legacy Flask behavior.

The guard is not registered in `aicrm_next.main`, so default Next runtime is not affected.

## Retired Route Behavior

Retired routes are D1-D6 readonly owners:

- Media readonly.
- Product readonly.
- Customer read model readonly.
- User Ops readonly.
- Questionnaire readonly.
- Automation readonly and legacy readonly aliases.

Retired readonly routes return HTTP 410 with JSON:

```json
{
  "ok": false,
  "error": "legacy_route_retired",
  "route_owner": "ai_crm_next",
  "legacy_fallback": true,
  "method": "GET",
  "path": "/api/customers",
  "reason": "retired_readonly_route",
  "next_owner": "aicrm_next.customer_read_model",
  "status": "retired"
}
```

Headers:

- `X-AICRM-Route-Owner: legacy_flask_retired`
- `X-AICRM-Next-Owner: <next owner>`

## Allowed Fallback Behavior

Allowed fallback routes are not blocked by the lockdown guard. This includes payment checkout/notify, questionnaire submit/OAuth, archive/contacts sync, OpenClaw push fallback, and operational diagnostics.

Allowed fallback is not production ownership. It remains explicit fallback until replacement evidence, rollback proof, and human signoff exist.

## Route Matrix Coverage

D8.2 uses the D8.1 route matrix as the documented source of route classes. The runtime module keeps static rules aligned with that matrix and the D8.2 checker verifies representative retired and allowed routes.

## Risk

- A broad retired pattern could accidentally block a needed fallback route.
- A missing retired pattern could allow stale readonly traffic to continue through legacy Flask.
- Operators could confuse allowed fallback with production ownership.

Mitigations:

- Allowed fallback is matched before retired routes.
- Tests cover D1-D6 retired groups and representative allowed fallback paths.
- Checker verifies retired response shape, headers, and allowed diagnostic route behavior.

## Rollback

D8.2 rollback is a code revert of `wecom_ability_service/legacy_lockdown.py` registration and related docs/tests/checker. It does not require data rollback because the guard does not execute writes.

## Non-Goals

- No deletion of `legacy_flask_app.py`.
- No deletion of `wecom_ability_service/`.
- No deletion of `openclaw_service/`.
- No production/deploy/nginx/systemd changes.
- No production traffic cutover.
- No real WeCom, OAuth, Payment, OpenClaw, MCP, cloud, archive, contacts, identity, or projection calls.
