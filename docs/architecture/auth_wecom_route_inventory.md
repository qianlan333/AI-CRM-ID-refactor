# Auth/wecom Wildcard Route Inventory

Scope: Legacy Exit group 11 inventories `/api/h5/wechat/oauth/{path:path}` and `/auth/wecom/{path:path}` wildcard surfaces, adds exact Next responses for known or probe paths, and keeps wildcard rollback for one validation cycle. This group does not delete wildcard routes, does not enable real OAuth or real WeCom calls, and does not handle payment, storage, OpenClaw, automation runtime, H5 submit business logic, or admin read/write.

Search command:

```bash
grep -R "/api/h5/wechat/oauth\|/auth/wecom" -n \
  aicrm_next docs tests scripts static templates frontend 2>/dev/null
```

Missing search directories: `static`, `templates`, and `frontend` do not exist at repository root; package-local templates under `aicrm_next/frontend_compat/templates` and `wecom_ability_service/templates` were included by the recursive search through `aicrm_next`.

| route | method | caller | current owner | expected owner | auth step | external side effect risk | replacement decision | delete decision | test coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/h5/wechat/oauth/start` | `GET`, `OPTIONS` | H5 questionnaire page builder in `aicrm_next/questionnaire/api.py`; tests/docs | `next_adapter` locked | `next_adapter` locked | Questionnaire OAuth start | medium / guarded | Already locked by group 10; verify boundary only | `deletion_locked` | `tests/test_questionnaire_oauth_registry_lifecycle.py`, `tests/test_auth_wecom_registry_lifecycle.py` |
| `/api/h5/wechat/oauth/callback` | `GET`, `OPTIONS` | H5 OAuth adapter callback URL in `aicrm_next/questionnaire/oauth.py`; tests/docs | `next_adapter` locked | `next_adapter` locked | Questionnaire OAuth callback | medium / guarded | Already locked by group 10; verify boundary only | `deletion_locked` | `tests/test_questionnaire_oauth_callback_adapter.py`, `tests/test_auth_wecom_registry_lifecycle.py` |
| `/auth/wecom/start` | `GET`, `OPTIONS` | Admin login docs/tests: `docs/admin_auth_rbac.md`, `wecom_ability_service/domains/admin_api_docs/service.py`, `tests/test_admin_slim_phase1.py`, `tests/test_admin_mcp_console.py`, `tests/test_admin_jobs_console.py`, `tests/test_automation_program_phase1.py`, `tests/automation_channel_admission_helpers.py` | wildcard / legacy Flask route | `next_native` exact response | Admin WeCom SSO start | high / real_blocked | Add exact Next blocked response; no real authorize URL call | `next_primary_with_legacy_rollback` | `tests/test_auth_wecom_exact_routes.py`, `tests/test_auth_wecom_no_real_external_calls.py`, `tests/test_auth_wecom_registry_lifecycle.py` |
| `/auth/wecom/callback` | `GET`, `OPTIONS` | Admin login docs/tests listed above | wildcard / legacy Flask route | `next_native` exact response | Admin WeCom SSO callback | high / real_blocked | Add exact Next blocked response; no code exchange | `next_primary_with_legacy_rollback` | `tests/test_auth_wecom_exact_routes.py`, `tests/test_auth_wecom_no_real_external_calls.py`, `tests/test_auth_wecom_registry_lifecycle.py` |
| `/api/h5/wechat/oauth/unknown` | `GET`, `OPTIONS` | No active production caller; smoke probe required by group 11 | wildcard | `next_native` exact response | Historical unknown H5 OAuth subpath | medium / guarded | Add explicit deprecated response, replacement `/api/h5/wechat/oauth/start` | `next_shadow` | `tests/test_auth_wecom_deprecated_routes.py`, `tests/test_auth_wecom_registry_lifecycle.py` |
| `/auth/wecom/unknown` | `GET`, `OPTIONS` | No active production caller; smoke probe required by group 11 | wildcard | `next_native` exact response | Historical unknown admin auth subpath | medium / guarded | Add explicit deprecated response, replacement `/auth/wecom/start` | `next_shadow` | `tests/test_auth_wecom_deprecated_routes.py`, `tests/test_auth_wecom_registry_lifecycle.py` |
| `/api/h5/wechat/oauth/{path:path}` | all | production compatibility wildcard in `aicrm_next/production_compat/api.py`; docs/tests inventory | `production_compat` wildcard | retained wildcard | Unknown H5 OAuth subpaths | medium / guarded | Retain for one validation cycle after exact responses | `active`, not deletion locked | `tests/test_auth_wecom_registry_lifecycle.py` |
| `/auth/wecom/{path:path}` | all | production compatibility wildcard in `aicrm_next/production_compat/api.py`; API docs classifier in `aicrm_next/frontend_compat/api_docs_view_model.py` | `production_compat` wildcard | retained wildcard | Unknown admin auth subpaths | high / real_blocked | Retain for one validation cycle after exact responses | `active`, not deletion locked | `tests/test_auth_wecom_registry_lifecycle.py` |

## A. Already Locked

- `/api/h5/wechat/oauth/start` and `/api/h5/wechat/oauth/callback` stay `deletion_locked`, `legacy_fallback_allowed=false`, and `adapter_mode=real_blocked`.
- These routes remain owned by the Questionnaire OAuth Next adapter and are not reimplemented in this group.

## B. Candidate Exact Routes

- `/auth/wecom/start` and `/auth/wecom/callback` are real admin auth surfaces in legacy Flask and docs/tests.
- In AI-CRM Next they now return explicit `external_call_blocked` responses with `route_owner=ai_crm_next`, `fallback_used=false`, and `real_external_call_executed=false`.
- This group does not exchange WeCom codes, build real authorize URLs, or mutate admin login sessions.

## C. Deprecated / Blocked

- `/api/h5/wechat/oauth/unknown` and `/auth/wecom/unknown` are explicit probe/deprecated responses.
- They return `410`, `error_code=auth_route_deprecated`, replacement route guidance, and no external call.

## D. Wildcard Retained

- `/api/h5/wechat/oauth/{path:path}` and `/auth/wecom/{path:path}` remain active wildcard rollback records for one validation cycle.
- Deletion is intentionally deferred until the auth/wecom wildcard deletion closeout after this group's exact response tests pass.
