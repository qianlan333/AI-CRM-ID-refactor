# Sidebar/Profile Route Matrix

This matrix documents the current compatibility owner and future Next exact
owner for WeCom sidebar, mobile binding, customer profile, and automation member
routes. It is plan/readiness evidence only and does not change runtime routing.

| Route pattern | Probe | Current owner | Next exact owner status | Future Next owner | Data source | Access | Write guard |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/sidebar/*` | `GET /sidebar/bind-mobile` | production_compat legacy_forward | missing Next exact owner | frontend_compat | production postgres via legacy facade | readonly page | n/a |
| `/api/sidebar/*` | `GET /api/sidebar/contact-binding-status` | production_compat legacy_forward | missing Next exact owner | identity_contact | identity_contact | read identity binding | n/a |
| `/api/sidebar/bind-mobile` | `POST /api/sidebar/bind-mobile` | production_compat legacy_forward | missing Next exact owner | identity_contact | identity_contact | write identity/mobile binding | guarded invalid-payload probe only |
| `/api/sidebar/lead-pool/*` | `GET /api/sidebar/lead-pool/status` | production_compat legacy_forward | missing Next exact owner | automation_engine | customer_read_model | readonly lead-pool status | n/a |
| `/api/sidebar/signup-tags/*` | `GET /api/sidebar/signup-tags/status` | production_compat legacy_forward | missing Next exact owner | customer_read_model | customer_read_model | readonly signup-tag status | n/a |
| `/api/sidebar/marketing-status*` | `GET /api/sidebar/marketing-status` | production_compat legacy_forward | missing Next exact owner | automation_engine | customer_read_model | readonly marketing status | n/a |
| `/api/admin/customers/profile` | `GET /api/admin/customers/profile` | production_compat legacy_forward | missing Next exact owner | customer_read_model | customer_read_model | readonly customer profile | n/a |
| `/api/admin/customers/profile/*` | `GET /api/admin/customers/profile/tags` | production_compat legacy_forward | missing Next exact owner | customer_read_model | customer_read_model | readonly profile sections | n/a |
| `/api/admin/automation-conversion/member` | `GET /api/admin/automation-conversion/member` | exact compatibility facade | exact compatibility facade | automation_engine | production postgres via legacy facade | readonly automation member detail | n/a |
| `/api/admin/automation-conversion/member/*` | `OPTIONS /api/admin/automation-conversion/member/put-in-pool` | production_compat legacy_forward | missing Next exact owner | automation_engine | production postgres via legacy facade | write automation member state | guarded non-writing route-existence probe only |

## Blocked Or Guarded Notes

- Sidebar mobile binding writes identity/mobile/binding data and must not become
  an unguarded production write.
- Lead-pool, signup-tag, marketing, and automation member state writes must stay
  guarded until a later task defines production audit, idempotency, rollback,
  and operator identity.
- External assistant/context push routes under the automation member family are
  blocked from real external side effects until separately approved.
