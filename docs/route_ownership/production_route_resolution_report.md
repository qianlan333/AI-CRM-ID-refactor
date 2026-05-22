# Production Route Resolution

- ok: `true`
- route_count: `199`
- production_compat_route_count: `78`
- production_compat_catch_all_count: `44`
- blockers: `0`

## Resolution Samples
- GET /health: `next` -> `aicrm_next.platform_foundation.api.health` (manifest `/health` / `next_exact`)
- GET /api/system/health: `next` -> `aicrm_next.platform_foundation.api.system_health` (manifest `/api/system/health` / `next_exact`)
- GET /api/customers: `next` -> `aicrm_next.customer_read_model.api.list_customers` (manifest `/api/customers` / `readonly_facade`)
- GET /api/customers/wx_ext_001: `next` -> `aicrm_next.customer_read_model.api.get_customer` (manifest `/api/customers/{external_userid}` / `readonly_facade`)
- GET /api/customers/wx_ext_001/timeline: `next` -> `aicrm_next.customer_read_model.api.get_customer_timeline` (manifest `/api/customers/{external_userid}/timeline` / `readonly_facade`)
- GET /api/messages/wx_ext_001/recent: `next` -> `aicrm_next.customer_read_model.api.get_recent_messages` (manifest `/api/messages/{external_userid}/recent` / `readonly_facade`)
- GET /api/admin/questionnaires: `next` -> `aicrm_next.questionnaire.api.list_questionnaires` (manifest `/api/admin/questionnaires*` / `guarded_preview`)
- GET /admin/questionnaires: `next` -> `aicrm_next.frontend_compat.legacy_routes.admin_questionnaires` (manifest `/admin/questionnaires` / `readonly_facade`)
- GET /admin/questionnaires/new: `next` -> `aicrm_next.frontend_compat.legacy_routes.admin_questionnaire_new` (manifest `/admin/questionnaires/new` / `readonly_facade`)
- GET /admin/questionnaires/21: `next` -> `aicrm_next.frontend_compat.legacy_routes.admin_questionnaire_detail` (manifest `/admin/questionnaires/{questionnaire_id}` / `readonly_facade`)
- GET /api/admin/questionnaires/21: `next` -> `aicrm_next.questionnaire.api.get_questionnaire` (manifest `/api/admin/questionnaires*` / `guarded_preview`)
- GET /api/h5/questionnaires/hxc-activation-v1: `next` -> `aicrm_next.questionnaire.api.public_get_questionnaire` (manifest `/api/h5/questionnaires*` / `guarded_preview`)
- GET /api/h5/wechat/oauth/start: `production_compat` -> `aicrm_next.production_compat.api.legacy_questionnaire_oauth_routes` (manifest `/api/h5/wechat/oauth*` / `legacy_forward`)
- GET /api/admin/automation-conversion/overview: `next` -> `aicrm_next.automation_engine.api.automation_overview` (manifest `/api/admin/automation-conversion*` / `guarded_preview`)
- POST /api/admin/automation-conversion/programs/3/setup/basic: `production_compat` -> `aicrm_next.production_compat.api.legacy_automation_workspace_routes` (manifest `/api/admin/automation-conversion/programs*` / `legacy_forward`)
- POST /api/admin/automation-conversion/settings/default-channel/generate: `production_compat` -> `aicrm_next.production_compat.api.legacy_automation_channel_settings_routes` (manifest `/api/admin/automation-conversion/settings*` / `legacy_forward`)
- GET /api/admin/automation-conversion/default-channel-settings: `production_compat` -> `aicrm_next.production_compat.api.legacy_automation_channel_settings_routes` (manifest `/api/admin/automation-conversion/default-channel-settings*` / `legacy_forward`)
- POST /api/admin/automation-conversion/default-channel-settings/generate-qr: `production_compat` -> `aicrm_next.production_compat.api.legacy_automation_channel_settings_routes` (manifest `/api/admin/automation-conversion/default-channel-settings*` / `legacy_forward`)
- GET /api/admin/automation-conversion/profile-segment-templates/options: `production_compat` -> `aicrm_next.production_compat.api.legacy_automation_workspace_routes` (manifest `/api/admin/automation-conversion/profile-segment-templates*` / `legacy_forward`)
- GET /api/admin/automation-conversion/agents/options: `production_compat` -> `aicrm_next.production_compat.api.legacy_automation_workspace_routes` (manifest `/api/admin/automation-conversion/agents*` / `legacy_forward`)
- POST /api/customer-automation/activation-webhook: `next` -> `aicrm_next.automation_engine.api.activation_webhook` (manifest `/api/customer-automation*` / `guarded_preview`)
- GET /admin/wechat-pay/products: `production_compat` -> `aicrm_next.production_compat.api.legacy_wechat_pay_product_admin_routes` (manifest `/admin/wechat-pay/products*` / `legacy_forward`)
- GET /admin/wechat-pay/products/new: `production_compat` -> `aicrm_next.production_compat.api.legacy_wechat_pay_product_admin_routes` (manifest `/admin/wechat-pay/products*` / `legacy_forward`)
- GET /api/admin/wechat-pay/products: `production_compat` -> `aicrm_next.production_compat.api.legacy_wechat_pay_product_admin_routes` (manifest `/api/admin/wechat-pay/products*` / `legacy_forward`)
- GET /api/admin/wechat-pay/products/1: `production_compat` -> `aicrm_next.production_compat.api.legacy_wechat_pay_product_admin_routes` (manifest `/api/admin/wechat-pay/products*` / `legacy_forward`)
- GET /api/admin/wechat-pay/products/1/share: `production_compat` -> `aicrm_next.production_compat.api.legacy_wechat_pay_product_admin_routes` (manifest `/api/admin/wechat-pay/products*` / `legacy_forward`)
- GET /p/prd_20260518095708_9f77db: `production_compat` -> `aicrm_next.production_compat.api.legacy_public_product_routes` (manifest `/p/{page_slug}` / `legacy_forward`)
- GET /pay/prd_20260518095708_9f77db: `production_compat` -> `aicrm_next.production_compat.api.legacy_public_product_routes` (manifest `/pay/{product_code}` / `legacy_forward`)
- GET /api/products/prd_20260518095708_9f77db: `production_compat` -> `aicrm_next.production_compat.api.legacy_public_product_routes` (manifest `/api/products*` / `legacy_forward`)
- GET /api/admin/image-library: `next` -> `aicrm_next.media_library.api.list_images` (manifest `/api/admin/image-library*` / `fake_adapter`)
- POST /api/admin/image-library/upload: `production_compat` -> `aicrm_next.production_compat.api.legacy_image_library_upload_route` (manifest `/api/admin/image-library/upload` / `legacy_forward`)
- GET /api/admin/image-library/image_masked_001: `next` -> `aicrm_next.media_library.api.get_image` (manifest `/api/admin/image-library*` / `fake_adapter`)
- POST /api/admin/automation-conversion/jobs/run-due: `production_compat` -> `aicrm_next.production_compat.api.legacy_production_compat_timer_routes` (manifest `/api/admin/automation-conversion/jobs/run-due*` / `scheduled_safe_mode`)
- POST /wecom/external-contact/callback: `production_compat` -> `aicrm_next.production_compat.api.wecom_callback_routes` (manifest `/wecom/external-contact/callback` / `legacy_forward`)
- POST /api/wecom/events: `production_compat` -> `aicrm_next.production_compat.api.wecom_callback_routes` (manifest `/api/wecom/events` / `legacy_forward`)
- GET /api/h5/wechat-pay/legacy-probe: `production_compat` -> `aicrm_next.production_compat.api.legacy_production_compat_routes` (manifest `/api/h5/wechat-pay*` / `legacy_forward`)
- GET /api/customers/automation/legacy-probe: `production_compat` -> `aicrm_next.production_compat.api.legacy_production_compat_routes` (manifest `/api/customers/automation*` / `legacy_forward`)
- GET /sidebar/bind-mobile: `next` -> `aicrm_next.frontend_compat.legacy_routes.sidebar_bind_mobile_page` (manifest `/sidebar/bind-mobile` / `readonly_facade`)
- GET /api/sidebar/contact-binding-status: `next` -> `aicrm_next.identity_contact.api.sidebar_contact_binding_status` (manifest `/api/sidebar/contact-binding-status` / `readonly_facade`)
- GET /api/sidebar/customer-context: `next` -> `aicrm_next.customer_read_model.api.get_sidebar_customer_context` (manifest `/api/sidebar/customer-context` / `readonly_facade`)
- GET /api/admin/customers/profile: `next` -> `aicrm_next.customer_read_model.api.get_admin_customer_profile` (manifest `/api/admin/customers/profile` / `readonly_facade`)
- GET /api/admin/customers/profile/tags: `next` -> `aicrm_next.customer_read_model.api.get_admin_customer_profile_tags` (manifest `/api/admin/customers/profile/tags` / `readonly_facade`)
- POST /api/sidebar/bind-mobile: `production_compat` -> `aicrm_next.production_compat.api.legacy_production_compat_routes` (manifest `/api/sidebar*` / `legacy_forward`)

## Shadowed Exact Routes
- POST /api/h5/questionnaires/{slug}/submit caught by `/api/h5/questionnaires/{slug}/submit`
- GET /api/h5/wechat/oauth/start caught by `/api/h5/wechat/oauth/start`
- GET /api/h5/wechat/oauth/callback caught by `/api/h5/wechat/oauth/callback`
- GET /api/admin/wechat-pay/products caught by `/api/admin/wechat-pay/products`
- GET /api/admin/wechat-pay/products/{product_id} caught by `/api/admin/wechat-pay/products/{path:path}`
- POST /api/admin/wechat-pay/products caught by `/api/admin/wechat-pay/products`
- POST /api/admin/wechat-pay/products/{product_id}/enable caught by `/api/admin/wechat-pay/products/{path:path}`
- POST /api/admin/wechat-pay/products/{product_id}/disable caught by `/api/admin/wechat-pay/products/{path:path}`
- GET /api/products/{page_slug} caught by `/api/products/{path:path}`
- GET /p/{page_slug} caught by `/p/{path:path}`
- GET /admin/wechat-pay/products caught by `/admin/wechat-pay/products`

## Blockers
