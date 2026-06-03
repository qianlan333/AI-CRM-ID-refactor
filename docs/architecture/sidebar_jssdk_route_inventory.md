# Sidebar JSSDK Route Inventory

Scope: Legacy Exit group 15 closeout locks `/api/sidebar/jssdk-config` to the Next JSSDK adapter and removes legacy rollback. This group does not enable real WeCom signing, token or ticket fetches, material send, tag mutation, payment, storage, OpenClaw, or automation runtime.

## Frontend ↔ API ↔ Backend Contract Matrix

| 页面/前端 | API | Backend | Contract | Smoke |
| --- | --- | --- | --- | --- |
| `/sidebar/bind-mobile` | 页面入口 | `aicrm_next.frontend_compat` route renders `sidebar_customer_workbench.html` | 页面非空，含 V2 workbench，含 `data-jssdk-config-url="/api/sidebar/jssdk-config"` | `curl` page smoke 200 |
| `sidebar_customer_workbench.html` | `data-jssdk-config-url` | template `aicrm_next/frontend_compat/templates/sidebar_customer_workbench.html` | 指向 `/api/sidebar/jssdk-config` | `grep` + smoke |
| `sidebar_workbench.js` | `GET /api/sidebar/jssdk-config?url=...` | JS fetch in `aicrm_next/frontend_compat/static/sidebar_workbench/sidebar_workbench.js` | 读取 `corp_id` / `agent_id` / `config` / `agent_config` with `timestamp`, `nonceStr`, `signature`, `jsApiList` | `grep` |
| JSSDK API | `GET` / `HEAD` / `OPTIONS` `/api/sidebar/jssdk-config` | Next adapter `aicrm_next.identity_contact.sidebar_jssdk` + `aicrm_next.integration_gateway.wecom_jssdk_adapter` | no real signing, `route_owner=ai_crm_next`, `fallback_used=false`, `real_external_call_executed=false`, no `X-AICRM-Compatibility-Facade`; GET returns `ok`, `appId`, `corpId`, `corp_id`, `agentId`, `agent_id`, `timestamp`, `nonceStr`, `signature`, `jsApiList`, `source_status`, `adapter_mode`, `config`, `agent_config`; HEAD returns 204; OPTIONS returns allowed methods | `curl` API smoke |

GET accepts `url`, optional `debug`, optional `agentid` / `agent_id` / `agentId`, and optional `corp_id` / `corpId` / `corpid`.

## Adapter Modes

| Mode | Default | Behavior |
| --- | --- | --- |
| `fake` | local/test default | Returns a deterministic signing contract for frontend initialization tests; no external call. |
| `sandbox` | explicit `AICRM_SIDEBAR_JSSDK_ADAPTER_MODE=sandbox` | Returns the same contract shape for sandbox checks; no external call. |
| `real_blocked` | production default | Returns a blocked-but-shaped contract with `external_call_blocked=true`; no external call. |
| `real_enabled` | requires explicit `AICRM_SIDEBAR_JSSDK_ADAPTER_MODE=real_enabled` and `AICRM_SIDEBAR_JSSDK_REAL_ENABLED=1` | Gated for a later PR; this group still records a blocked attempt and does not fetch real signing material. |

## Boundaries

1. The Next route is registered before `production_compat_router`, so page/API smoke must not hit `X-AICRM-Compatibility-Facade`.
2. The legacy production_compat exact route has been removed; `/api/sidebar/jssdk-config` is Next adapter only and `legacy_fallback_allowed=false`.
3. Real WeCom signing, token fetch, ticket fetch, material send, tag mutation, payment, storage, OpenClaw, and automation runtime are out of scope.
4. Every adapter response records an AuditLedger blocked/planned attempt with `real_external_call_executed=false`.
