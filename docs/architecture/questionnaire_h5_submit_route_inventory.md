# Questionnaire H5 Submit Route Inventory

Scope: Legacy Exit group 9 moves public H5 submit and client diagnostics writes to the Next CommandBus. This group does not delete the legacy rollback and does not handle OAuth/auth, real WeCom tag mutation, real external push execution, payment, storage, OpenClaw, or automation runtime execution.

| route | method | current owner | expected owner | write type | identity source | external side effect risk | command name | side effect plan | replacement decision | delete decision | test coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/h5/questionnaires/{slug}/submit` | `POST` | Next exact route, previously shadowed by `production_compat` when legacy facade was enabled | `next_command` | form submission, answer validation, result calculation, identity binding payload, submission projection | anonymous, `identity`, `respondent_identity`, top-level `external_userid` / `openid` / `unionid` / `mobile` | medium / guarded | `questionnaire.h5.submit` | `questionnaire.h5.submit.side_effects`, `adapter_mode=real_blocked`, `requires_approval=true`, `real_external_call_executed=false` | Next CommandBus primary; legacy rollback retained for the later deletion group | `next_primary_with_legacy_rollback`; not deletion_locked | `tests/test_questionnaire_h5_submit_commands.py`, `tests/test_questionnaire_h5_submit_idempotency.py`, `tests/test_questionnaire_h5_submit_no_real_side_effects.py`, `tests/test_questionnaire_h5_submit_no_fixture_production.py` |
| `/api/h5/questionnaires/{slug}/client-diagnostics` | `POST` | `production_compat` legacy forward | `next_command` | client error / environment diagnostic write | anonymous, `identity`, `respondent_identity` | low / guarded | `questionnaire.h5.client_diagnostics` | none; AuditLedger only | Next CommandBus/AuditLedger primary; unresolved slug is recorded without external calls | `next_primary_with_legacy_rollback`; not deletion_locked | `tests/test_questionnaire_h5_client_diagnostics.py`, `tests/test_questionnaire_h5_submit_registry_lifecycle.py` |

## A. H5 Submit

- Submit validates the questionnaire slug exists and is enabled.
- `answers` must be a JSON object and required answers are validated with the existing questionnaire domain rules.
- Identity may be anonymous or supplied with `external_userid`, `openid`, `unionid`, `mobile`, and `respondent_key`.
- Result calculation uses the existing score/tag rules and writes a local submission projection through the Next questionnaire repository in fixture mode.
- Production writes that cannot use a real Next submission model return controlled `production_unavailable`; fixture data is not used as production success.
- Response includes `ok`, `command_id`, `submission_id`, `questionnaire_id`, `slug`, `result`, `source_status=next_command`, `route_owner=ai_crm_next`, `fallback_used=false`, `real_external_call_executed=false`.

## B. Diagnostics

- Diagnostics accepts client payloads even when the slug is unresolved and records `unresolved_slug=true`.
- Diagnostics records AuditLedger evidence and an in-memory diagnostics projection in local/test.
- Response includes `ok`, `command_id`, `diagnostic_id`, `source_status=next_command`, `route_owner=ai_crm_next`, `fallback_used=false`, `real_external_call_executed=false`.

## C. Out Of Scope

| surface | decision |
| --- | --- |
| `/api/h5/wechat/oauth/start` | Out of scope; stays legacy/OAuth group and is not deletion_locked by this group. |
| `/api/h5/wechat/oauth/callback` | Out of scope; stays legacy/OAuth group and is not deletion_locked by this group. |
| `/auth/wecom/*` | Out of scope. |
| real WeCom tag mutation | SideEffectPlan only; no real tag mutation executes. |
| external push real execution | SideEffectPlan only; no real external push executes. |
| payment / storage / OpenClaw / automation runtime | Out of scope; no real runtime execution added. |
| admin read/write | Already deletion_locked; this group does not change the lock. |
