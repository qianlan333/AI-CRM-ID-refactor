# Next Production Route Compatibility Matrix

| route | method | legacy_status | next_status | production_owner | implementation_mode | cutover_status | blocker |
|---|---|---|---|---|---|---|---|
| /admin | GET | active legacy admin shell | Next owns via frontend compatibility shell | ai_crm_next | native_next | ready_for_server_verification | keep 5013 callback fallback only |
| /admin/customers | GET | active customer admin page | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | production DATABASE_URL required |
| /api/customers* | GET/POST | active customer read/write APIs | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | production DATABASE_URL required |
| /api/messages/*/recent | GET | archive/customer read fallback | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | production DATABASE_URL required |
| /admin/questionnaires* | GET/POST | active questionnaire admin | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | production DATABASE_URL required |
| /api/admin/questionnaires* | GET/POST/PUT/DELETE | active questionnaire API | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | production DATABASE_URL required |
| /s/* | GET/POST | active public questionnaire H5 | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | OAuth env required for live OAuth |
| /api/h5/questionnaires* | GET/POST | active public questionnaire API | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | production DATABASE_URL required |
| /api/h5/wechat/oauth/* | GET | active OAuth fallback | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | real OAuth env required |
| /auth/wecom/* | GET | active admin SSO fallback | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | real WeCom env required |
| /admin/wechat-pay/products | GET | active product admin page | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | production DATABASE_URL required |
| /api/admin/wechat-pay/* | GET/POST/PUT/DELETE | active commerce admin API | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | production DATABASE_URL required |
| /api/h5/wechat-pay/jsapi/orders | POST | active JSAPI checkout | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | payment env/signing required |
| /api/h5/wechat-pay/notify | POST | active payment notify | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | signature validation required |
| /api/h5/alipay/* | GET/POST | active Alipay H5 fallback | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | Alipay env/signing required |
| /p/* | GET | active public product page | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | production DATABASE_URL required |
| /api/products/* | GET | active public product API | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | production DATABASE_URL required |
| /api/orders/* | GET | active order status API | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | production DATABASE_URL required |
| /admin/image-library | GET | active media admin page | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | production DATABASE_URL required |
| /api/admin/image-library* | GET/POST/PUT/DELETE | active image library API | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | upload side effects must keep existing guards |
| /admin/attachment-library | GET | active attachment admin page | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | production DATABASE_URL required |
| /api/admin/attachment-library* | GET/POST/PUT/DELETE | active attachment API | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | upload side effects must keep existing guards |
| /admin/miniprogram-library | GET | active miniprogram admin page | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | production DATABASE_URL required |
| /api/admin/miniprogram-library* | GET/POST/PUT/DELETE | active miniprogram API | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | production DATABASE_URL required |
| /admin/automation-conversion | GET | active automation admin page | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | production DATABASE_URL required |
| /api/admin/automation-conversion* | GET/POST/PUT/DELETE | active automation APIs | Next owns in production via facade | ai_crm_next | legacy_facade | ready_for_server_verification | internal/external writes keep existing guards |
| /api/admin/automation-conversion/reply-monitor/run-due | POST | legacy timer endpoint | Next owns in production via facade plus token guard | ai_crm_next | legacy_facade | ready_for_server_verification | enable timer only after checker PASS on server |
| /api/admin/automation-conversion/reply-monitor/capture | POST | legacy timer endpoint | Next owns in production via facade plus token guard | ai_crm_next | legacy_facade | ready_for_server_verification | enable timer only after checker PASS on server |
| /api/admin/automation-conversion/jobs/run-due | POST | legacy timer endpoint | Next owns in production via facade plus token guard | ai_crm_next | legacy_facade | ready_for_server_verification | enable timer only after checker PASS on server |
| /api/admin/cloud-orchestrator/campaigns/run-due | POST | legacy timer endpoint | Next owns in production via facade plus token guard | ai_crm_next | legacy_facade | ready_for_server_verification | enable timer only after checker PASS on server |
| /wecom/external-contact/callback | GET/POST | legacy callback; 5013 fallback retained | Next owns in production via callback facade | ai_crm_next | legacy_facade | ready_for_server_verification | keep 5013 fallback until observation window |
| /api/wecom/events | GET/POST | legacy callback; 5013 fallback retained | Next owns in production via callback facade | ai_crm_next | legacy_facade | ready_for_server_verification | keep 5013 fallback until observation window |
| user ops admin/API routes | GET/POST | retired readonly owner with replacement contract | Next native/fixture currently remains local mode; production facade covers /admin shell | ai_crm_next | native_next | ready_for_server_verification | no unexplained production 404 allowed |

Notes:

- `allowed production owner = ai_crm_next`; legacy code is invoked only behind the explicit Next compatibility boundary.
- `implementation_mode=legacy_facade` means Next owns the HTTP route and forwards into existing legacy domain/runtime code so production data and side-effect guards are preserved.
- This matrix does not approve removal of the 5013 callback fallback.
