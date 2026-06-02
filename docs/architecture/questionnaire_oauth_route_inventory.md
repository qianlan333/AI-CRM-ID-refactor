# Questionnaire OAuth Route Inventory

Scope: Legacy Exit group 10 moves Questionnaire H5 OAuth/auth transport to the Next OAuth adapter. This group does not delete OAuth/auth legacy rollback, does not enable real OAuth by default, and does not handle real WeCom tag mutation, external push execution, payment, storage, OpenClaw, automation runtime, admin read/write, or H5 submit business rollback.

| route | method | current owner | expected owner | oauth step | identity/session effect | external side effect risk | adapter mode | replacement decision | delete decision | test coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/h5/wechat/oauth/start` | `GET`, `OPTIONS` | Next exact route, legacy rollback retained | `next_adapter` | state generation, redirect construction, redirect allowlist | no session yet | medium / guarded | `fake` local/test, `real_blocked` production default | Next OAuth adapter primary; no real OAuth by default | `next_primary_with_legacy_rollback` | `tests/test_questionnaire_oauth_start_adapter.py`, `tests/test_questionnaire_oauth_state_security.py`, `tests/test_questionnaire_oauth_no_real_external_calls.py` |
| `/api/h5/wechat/oauth/callback` | `GET`, `OPTIONS` | Next exact route, legacy rollback retained | `next_adapter` | code/state verification, fake/sandbox identity, replay protection, audit | signed identity session cookie | medium / guarded | `fake` local/test, `real_blocked` production default | Next OAuth adapter primary; no real OAuth by default | `next_primary_with_legacy_rollback` | `tests/test_questionnaire_oauth_callback_adapter.py`, `tests/test_questionnaire_oauth_session_cookie.py`, `tests/test_questionnaire_oauth_registry_lifecycle.py` |
| `/api/h5/wechat/oauth/{path:path}` | all | production compatibility wildcard | inventory only | unknown OAuth subpath | unknown | guarded | `real_blocked` | retained as wildcard rollback / unknown-surface inventory | `active` | `tests/test_questionnaire_oauth_inventory.py` |
| `/auth/wecom/{path:path}` | all | production compatibility wildcard | inventory only | admin/WeCom auth wildcard | legacy admin auth session | guarded | `real_blocked` | retained out of scope; not part of questionnaire H5 OAuth adapter replacement | `active` | `tests/test_questionnaire_oauth_inventory.py` |

## A. OAuth Start

- Builds a signed state with `slug`, redirect target, nonce, issued-at, expiry, and adapter mode.
- Enforces redirect allowlist. Relative `/...` targets are allowed; absolute redirects require `AICRM_QUESTIONNAIRE_OAUTH_REDIRECT_ALLOWLIST`.
- Returns `source_status=next_oauth_adapter`, `route_owner=ai_crm_next`, `fallback_used=false`, and `real_external_call_executed=false`.
- Local/test defaults to `fake`; production defaults to `real_blocked`.

## B. OAuth Callback

- Verifies signed state, nonce, expiry, and replay status.
- Fake/sandbox modes create deterministic test identity without network calls.
- `real_blocked` records a controlled blocked result and does not exchange code with WeChat.
- Successful callback creates a signed `questionnaire_h5_identity` cookie and records AuditLedger evidence.
- Error paths write diagnostics without logging sensitive tokens.

## C. Wildcard / Out Of Scope

- `/api/h5/wechat/oauth/{path:path}` remains retained legacy rollback for unknown OAuth subpaths.
- `/auth/wecom/*` remains out of scope and is not deletion locked by this group.
- Real OAuth enablement requires explicit `AICRM_QUESTIONNAIRE_OAUTH_ADAPTER_MODE` plus `AICRM_QUESTIONNAIRE_OAUTH_ENABLE_REAL`; this PR does not enable it.
