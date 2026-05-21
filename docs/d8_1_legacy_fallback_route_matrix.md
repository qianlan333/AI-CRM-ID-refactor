# D8.1 Legacy Fallback Route Matrix

Status: planning/readiness only.

This matrix is the D8.1 docs source for future route/fallback lockdown planning. It does not register runtime enforcement and does not change route behavior.

| Category | Legacy owner examples | D7 replacement state | D8.1 action | Future evidence required |
| --- | --- | --- | --- | --- |
| Payment checkout/notify/admin | `wecom_ability_service/http/wechat_pay.py`, `alipay_pay.py`, admin payment modules | Fake/staging-disabled adapter contracts only | keep fallback | Real provider evidence, callback proof, observation, rollback proof, signoff. |
| Questionnaire submit/OAuth/write/external push | Questionnaire legacy HTTP/domain modules | Fake/staging-disabled adapter contracts only | keep fallback | Real submit/OAuth/external push evidence, observation, rollback proof, signoff. |
| User Ops write/WeCom dispatch/deferred jobs | User Ops services, task routes, job routes | Fake/staging-disabled adapter contracts only | keep fallback | Real write/dispatch/job evidence, observation, rollback proof, signoff. |
| Automation write/webhook/runtime/agent/OpenClaw | Automation legacy HTTP/domain modules, `openclaw_service/` | Fake/staging-disabled adapter contracts only | keep fallback | Real runtime/OpenClaw evidence, observation, rollback proof, signoff. |
| Archive/contacts/identity | `archive.py`, `contacts.py`, `identity.py` | Fake/staging-disabled adapter contracts only | keep fallback | Real sync/mapping evidence, observation, rollback proof, signoff. |
| Media cloud/WeCom upload | Legacy media libraries and upload helpers | Fake/staging-disabled adapter contracts only | keep fallback | Real upload evidence, observation, rollback proof, signoff. |
| MCP/OpenClaw adapter | `wecom_ability_service/mcp_adapter.py`, `openclaw_service/` | Fake/staging-disabled adapter contracts only | keep fallback | Real MCP/OpenClaw evidence, observation, rollback proof, signoff. |
| Legacy shell entry | `legacy_flask_app.py`, `app.py run-legacy` | Explicit fallback remains required | keep fallback | Next-only deploy path, no legacy route hits, rollback proof, signoff. |

## Runtime Enforcement

No runtime guard is registered in D8.1 planning. Future enforcement must be introduced by a separate approved phase and checked against this matrix or its successor.
