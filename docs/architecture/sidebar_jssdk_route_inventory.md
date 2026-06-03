# Sidebar JSSDK Route Inventory

Scope: Legacy Exit group 15 moves `/api/sidebar/jssdk-config` to a Next JSSDK adapter while retaining legacy rollback. This group does not enable real WeCom signing, token or ticket fetches, material send, tag mutation, payment, storage, OpenClaw, or automation runtime.

## Frontend ↔ API ↔ Backend Contract Matrix

| Frontend surface | Frontend file | API | Query parameters | Response fields | Backend owner | Adapter mode | Smoke |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/sidebar/bind-mobile` V2 page | `aicrm_next/frontend_compat/legacy_routes.py` renders `sidebar_customer_workbench.html` | page shell only | `external_userid`, `owner_userid`, `v` | HTML contains `data-jssdk-config-url="/api/sidebar/jssdk-config"` | `aicrm_next.frontend_compat` | none | page smoke 200 |
| `sidebar_customer_workbench.html` | `aicrm_next/frontend_compat/templates/sidebar_customer_workbench.html` | `/api/sidebar/jssdk-config` via data attribute | none in template | `data-jssdk-config-url` points to Next API | `aicrm_next.frontend_compat` | none | static contract test |
| Workbench JS JSSDK init | `aicrm_next/frontend_compat/static/sidebar_workbench/sidebar_workbench.js` | `GET /api/sidebar/jssdk-config` | `url=window.location.href.split("#")[0]`; optional `debug`, `agentid`, `corp_id` accepted by API | `corp_id`, `agent_id`, `config.timestamp`, `config.nonceStr`, `config.signature`, `agent_config.timestamp`, `agent_config.nonceStr`, `agent_config.signature` | `aicrm_next.identity_contact.sidebar_jssdk` | `fake` locally, `real_blocked` in production by default | API smoke 200 |
| JSSDK config API | `aicrm_next/identity_contact/sidebar_jssdk.py` | `GET /api/sidebar/jssdk-config` | `url`, `debug`, `agentid` / `agent_id`, `corp_id` / `corpId` / `corpid` | `ok`, `appId`, `corpId`, `corp_id`, `agentId`, `agent_id`, `timestamp`, `nonceStr`, `signature`, `jsApiList`, `source_status`, `adapter_mode`, `route_owner`, `fallback_used`, `real_external_call_executed`, plus legacy-compatible `config` and `agent_config` | `aicrm_next.integration_gateway.wecom_jssdk_adapter` | `fake`, `sandbox`, `real_blocked`, `real_enabled` gated | API smoke 200 |
| JSSDK preflight | `aicrm_next/identity_contact/sidebar_jssdk.py` | `OPTIONS /api/sidebar/jssdk-config` | none | Next diagnostics, allowed methods, `fallback_used=false`, `real_external_call_executed=false` | `aicrm_next.identity_contact.sidebar_jssdk` | `real_blocked` diagnostic | OPTIONS smoke 200 |
| JSSDK HEAD | `aicrm_next/identity_contact/sidebar_jssdk.py` | `HEAD /api/sidebar/jssdk-config` | optional `url` | empty body, Next route headers, no compatibility facade | `aicrm_next.identity_contact.sidebar_jssdk` | no external call | HEAD smoke 204 |

## Adapter Modes

| Mode | Default | Behavior |
| --- | --- | --- |
| `fake` | local/test default | Returns a deterministic signing contract for frontend initialization tests; no external call. |
| `sandbox` | explicit `AICRM_SIDEBAR_JSSDK_ADAPTER_MODE=sandbox` | Returns the same contract shape for sandbox checks; no external call. |
| `real_blocked` | production default | Returns a blocked-but-shaped contract with `external_call_blocked=true`; no external call. |
| `real_enabled` | requires explicit `AICRM_SIDEBAR_JSSDK_ADAPTER_MODE=real_enabled` and `AICRM_SIDEBAR_JSSDK_REAL_ENABLED=1` | Gated for a later PR; this group still records a blocked attempt and does not fetch real signing material. |

## Boundaries

1. The Next route is registered before `production_compat_router`, so page/API smoke must not hit `X-AICRM-Compatibility-Facade`.
2. The legacy production_compat route remains registered for rollback in this group.
3. Real WeCom signing, token fetch, ticket fetch, material send, tag mutation, payment, storage, OpenClaw, and automation runtime are out of scope.
4. Every adapter response records an AuditLedger blocked/planned attempt with `real_external_call_executed=false`.
