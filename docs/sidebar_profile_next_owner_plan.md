# Sidebar/Profile Next Owner Plan

## Business Impact

WeCom sidebar is the daily entry point for sales and operations teams to identify
customers, bind mobile numbers, and open student/customer detail pages inside
WeCom. This plan prevents AI-CRM Next cutover from turning sidebar/profile
routes into 404/500 failures, while preparing a controlled graduation from
legacy compatibility routes to exact Next owners.

## Current State

- `GET /sidebar/bind-mobile`, `GET /api/sidebar/contact-binding-status`,
  `GET /api/sidebar/customer-context`, `GET /api/admin/customers/profile`, and
  `GET /api/admin/customers/profile/tags` now have AI-CRM Next exact readonly
  owners.
- Remaining `/sidebar/*`, `/api/sidebar/*`, and
  `/api/admin/customers/profile*` paths continue to use `production_compat`
  legacy forwarding until they receive exact owner evidence.
- `/api/sidebar/bind-mobile` is a write-capable identity/mobile binding route
  and remains behind the legacy compatibility facade until a guarded
  `identity_contact` command exists.
- `/api/sidebar/lead-pool/*`, `/api/sidebar/signup-tags/*`, and
  `/api/sidebar/marketing-status*` remain compatibility routes for lead-pool,
  signup status, and marketing context surfaces.
- `/api/admin/automation-conversion/member` is an exact compatibility facade in
  `aicrm_next.production_compat.api`.
- `/api/admin/automation-conversion/member/*` write/action routes remain
  `production_compat` legacy forwarding.
- No runtime route behavior changes are made by this plan.

## Future Owner Plan

| Route family | Current owner | Future Next owner | Data source | Access |
| --- | --- | --- | --- | --- |
| `/sidebar/bind-mobile` | next exact readonly | frontend_compat | frontend_compat readonly page | readonly page |
| `/api/sidebar/contact-binding-status` | next exact readonly | identity_contact | identity_contact with legacy production facade fallback | readonly identity binding |
| `/api/sidebar/customer-context` | next exact readonly | customer_read_model | customer_read_model with legacy production facade fallback | readonly customer context |
| `/api/sidebar/*` remaining paths | production_compat legacy_forward | identity_contact / customer_read_model / automation_engine | identity_contact and customer_read_model | readonly plus guarded writes |
| `/api/admin/customers/profile` | next exact readonly | customer_read_model | customer_read_model with legacy production facade fallback | readonly profile |
| `/api/admin/customers/profile/tags` | next exact readonly | customer_read_model | customer_read_model with legacy production facade fallback | readonly sections |
| `/api/admin/customers/profile/*` remaining paths | production_compat legacy_forward | customer_read_model | customer_read_model | readonly sections |
| `/api/admin/automation-conversion/member` | exact compatibility facade | automation_engine | production postgres via legacy facade | readonly member detail |
| `/api/admin/automation-conversion/member/*` | production_compat legacy_forward | automation_engine | production postgres via legacy facade | guarded writes |

## Migration Steps

1. Keep current `production_compat` fallback live while adding Next exact read
   contracts for sidebar identity, profile, and automation member data.
2. Move readonly profile sections to `customer_read_model` projections.
3. Move mobile binding and identity resolution to `identity_contact`, with
   production writes blocked until a separate approval defines audit,
   idempotency, rollback, and operator identity.
4. Move automation member state actions to `automation_engine` guarded command
   APIs. Invalid or dry-run probes must remain non-writing.
5. Update the route ownership manifest before moving any route from
   `production_compat` to Next exact owner.
6. Only after checker evidence is green, narrow the relevant wildcard
   production compatibility route.

## Safety Rules

- Write operations that touch identity, mobile binding, lead-pool status,
  signup tags, marketing status, or automation member state must stay guarded.
- No real production write is enabled by this plan.
- No real external call is enabled by this plan.
- No deploy, nginx, systemd, or legacy fallback behavior is changed by this
  plan.

## Readiness Evidence

Run:

```bash
.venv/bin/python tools/check_sidebar_profile_next_owner_readiness.py \
  --output-md /tmp/sidebar_profile_next_owner_readiness.md \
  --output-json /tmp/sidebar_profile_next_owner_readiness.json
```

The checker verifies that current compatibility routes do not return 404/5xx,
expose an explicit route owner/facade, and do not leak fixture markers.
