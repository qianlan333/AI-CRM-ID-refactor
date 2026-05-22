# D8 Legacy Shell Allowed Fallback Matrix

Status: planning/readiness only.

This matrix lists fallback surfaces that must remain allowed while D8 is only in planning. It is a documentation source for D8.0 readiness; it is not runtime enforcement.

| Fallback surface | Current owner | Allowed while planning? | Removal blocker |
| --- | --- | --- | --- |
| Explicit legacy Flask runner | `legacy_flask_app.py` | yes | Rollback still requires explicit fallback access. |
| Legacy Flask app factory | `wecom_ability_service/__init__.py` | yes | App factory has not moved and shell retirement is not approved. |
| Legacy HTTP route registrar | `wecom_ability_service/http/__init__.py` | yes | D7 real replacement evidence and route-hit observation are missing. |
| Payment checkout/notify/admin fallback | `wecom_ability_service/http/wechat_pay.py`, `wecom_ability_service/http/alipay_pay.py`, admin payment modules | yes | Real payment adapter evidence, provider callback proof, rollback proof, and signoff are missing. |
| Questionnaire submit/OAuth/write/external push fallback | Questionnaire legacy HTTP/domain modules | yes | Real submit/OAuth/external push evidence and production observation are missing. |
| User Ops write/dispatch/deferred jobs fallback | User Ops legacy services and task/job routes | yes | Real write/dispatch/job evidence and observation are missing. |
| Automation write/webhook/runtime/agent/OpenClaw fallback | Automation legacy HTTP/domain modules plus D7.5/D7.7 fake adapter boundary | yes | Real automation runtime and OpenClaw evidence are missing; repo-side `openclaw_service/` is absent after D9.6. |
| Archive/contacts/identity fallback | `wecom_ability_service/http/archive.py`, `contacts.py`, `identity.py` | yes | Real sync/mapping evidence and observation are missing. |
| Media cloud/WeCom upload fallback | Legacy media library and upload helpers | yes | Real provider upload evidence and rollback proof are missing. |
| MCP/OpenClaw adapter fallback | `wecom_ability_service/mcp_adapter.py` plus D7.7 fake adapter boundary | yes | Real MCP/OpenClaw evidence and signoff are missing; repo-side `openclaw_service/` is absent after D9.6. |

## Source-Of-Truth Note

While D8 is planning-only, this matrix is the docs source for allowed fallback categories. Runtime ownership remains in existing code paths; no runtime block or route guard is registered by this matrix.
