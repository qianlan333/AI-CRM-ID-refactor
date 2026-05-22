# Production Route Resolution

- ok: `true`
- route_count: `148`
- production_compat_route_count: `35`
- production_compat_catch_all_count: `22`
- blockers: `0`

## Resolution Samples
- GET /health: `next` -> `aicrm_next.platform_foundation.api.health` (manifest `/health` / `next_exact`)
- GET /api/system/health: `next` -> `aicrm_next.platform_foundation.api.system_health` (manifest `/api/system/health` / `next_exact`)
- GET /api/customers: `next` -> `aicrm_next.customer_read_model.api.list_customers` (manifest `/api/customers` / `readonly_facade`)
- GET /api/customers/wx_ext_001: `next` -> `aicrm_next.customer_read_model.api.get_customer` (manifest `/api/customers/{external_userid}` / `readonly_facade`)
- GET /api/customers/wx_ext_001/timeline: `next` -> `aicrm_next.customer_read_model.api.get_customer_timeline` (manifest `/api/customers/{external_userid}/timeline` / `readonly_facade`)
- GET /api/messages/wx_ext_001/recent: `next` -> `aicrm_next.customer_read_model.api.get_recent_messages` (manifest `/api/messages/{external_userid}/recent` / `readonly_facade`)
- GET /api/admin/questionnaires: `next` -> `aicrm_next.questionnaire.api.list_questionnaires` (manifest `/api/admin/questionnaires*` / `guarded_preview`)
- GET /api/h5/questionnaires/hxc-activation-v1: `next` -> `aicrm_next.questionnaire.api.public_get_questionnaire` (manifest `/api/h5/questionnaires*` / `guarded_preview`)
- GET /api/h5/wechat/oauth/start: `next` -> `aicrm_next.questionnaire.api.wechat_oauth_start` (manifest `/api/h5/wechat/oauth*` / `fake_adapter`)
- GET /api/admin/automation-conversion/overview: `next` -> `aicrm_next.automation_engine.api.automation_overview` (manifest `/api/admin/automation-conversion*` / `guarded_preview`)
- POST /api/customer-automation/activation-webhook: `next` -> `aicrm_next.automation_engine.api.activation_webhook` (manifest `/api/customer-automation*` / `guarded_preview`)
- GET /api/admin/wechat-pay/products: `next` -> `aicrm_next.commerce.api.list_products` (manifest `/api/admin/wechat-pay*` / `fake_adapter`)
- GET /api/admin/wechat-pay/products/prod_001: `next` -> `aicrm_next.commerce.api.get_product` (manifest `/api/admin/wechat-pay*` / `fake_adapter`)
- GET /api/admin/image-library: `next` -> `aicrm_next.media_library.api.list_images` (manifest `/api/admin/image-library*` / `fake_adapter`)
- GET /api/admin/image-library/image_masked_001: `next` -> `aicrm_next.media_library.api.get_image` (manifest `/api/admin/image-library*` / `fake_adapter`)
- POST /api/admin/automation-conversion/jobs/run-due: `production_compat` -> `aicrm_next.production_compat.api.legacy_production_compat_timer_routes` (manifest `/api/admin/automation-conversion/jobs/run-due*` / `scheduled_safe_mode`)
- POST /wecom/external-contact/callback: `production_compat` -> `aicrm_next.production_compat.api.wecom_callback_routes` (manifest `/wecom/external-contact/callback` / `legacy_forward`)
- POST /api/wecom/events: `production_compat` -> `aicrm_next.production_compat.api.wecom_callback_routes` (manifest `/api/wecom/events` / `legacy_forward`)
- GET /api/h5/wechat-pay/legacy-probe: `production_compat` -> `aicrm_next.production_compat.api.legacy_production_compat_routes` (manifest `/api/h5/wechat-pay*` / `legacy_forward`)
- GET /api/customers/automation/legacy-probe: `production_compat` -> `aicrm_next.production_compat.api.legacy_production_compat_routes` (manifest `/api/customers/automation*` / `legacy_forward`)

## Shadowed Exact Routes
- none

## Blockers
