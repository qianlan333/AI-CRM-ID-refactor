# D7.2 Questionnaire Submit / OAuth / WeCom Tag Adapter Contract

## Scope

D7.2 establishes the adapter boundary for Questionnaire submit side effects, WeChat OAuth, WeCom tag operations, and questionnaire external push. This slice does not enable real WeChat OAuth, real WeCom tag writes, real webhook delivery, production route changes, or production traffic cutover.

## Implemented Adapters

| adapter | owning_context | methods | default_mode | real_external_call_status |
| --- | --- | --- | --- | --- |
| WeChatOAuthAdapter | `aicrm_next.integration_gateway` | `build_authorize_url`, `exchange_code`, `fetch_userinfo`, `resolve_oauth_identity` | `fake` | not implemented and not executed |
| WeComTagAdapter | `aicrm_next.integration_gateway` | `mark_external_contact_tags`, `unmark_external_contact_tags`, `validate_tag_ids`, `build_tag_operation_preview` | `fake` | not implemented and not executed |
| QuestionnaireExternalPushAdapter | `aicrm_next.integration_gateway` | `push_submission_event`, `push_score_result_event`, `retry_push_event`, `build_push_preview` | `fake` | not implemented and not executed |
| QuestionnaireSubmitSideEffectGateway | `aicrm_next.integration_gateway` | `apply_tags`, `emit_external_push`, `emit_automation_questionnaire_result`, `record_side_effect_audit` | fake boundary | real side effects not executed |

## Stable Result Shape

Every adapter method returns:

| field | meaning |
| --- | --- |
| `ok` | adapter success flag |
| `adapter` | adapter name |
| `mode` | `fake`, `disabled`, `staging`, or `production` |
| `operation` | method operation name |
| `idempotency_key` | deterministic guard key |
| `target` | sanitized operation target such as openid, unionid, external_userid, questionnaire_id, submission_id, tag_ids, or webhook_url |
| `result` | deterministic fake result |
| `audit_id` | in-memory audit event id |
| `side_effect_executed` | always `false` in D7.2 |
| `error_code` | stable machine-readable error |
| `error_message` | stable human-readable error |

Targets must not include real secrets, access tokens, app secrets, or production credentials.

## Mode Behavior

| mode | behavior | side_effect_executed |
| --- | --- | --- |
| fake | deterministic fake OAuth identity, tag operation, push result, and submit side-effect audit | false |
| disabled | stable `adapter_disabled` error | false |
| staging | staging-shaped fake result only; no OAuth, WeCom, or webhook call | false |
| production | fails closed without explicit env flag; real outbound implementation is absent in D7.2 | false |

## Env Flags

| flag | default | purpose |
| --- | --- | --- |
| `AICRM_NEXT_WECHAT_OAUTH_MODE` | `fake` | OAuth adapter mode |
| `AICRM_NEXT_WECOM_TAG_MODE` | `fake` | WeCom tag adapter mode |
| `AICRM_NEXT_QUESTIONNAIRE_WEBHOOK_MODE` | `fake` | questionnaire external push adapter mode |
| `AICRM_NEXT_ENABLE_REAL_WECHAT_OAUTH` | unset / false | required before any future real OAuth implementation can run |
| `AICRM_NEXT_ENABLE_REAL_WECOM_TAG` | unset / false | required before any future real WeCom tag implementation can run |
| `AICRM_NEXT_ENABLE_REAL_QUESTIONNAIRE_WEBHOOK` | unset / false | required before any future real webhook delivery can run |

Production mode without the explicit enable flag returns `production_guard_failed`. Production mode with the explicit flag still returns `production_not_implemented` in D7.2.

## Submit Side-Effect Gateway

Questionnaire submit stores the fake submission as before, then routes the side-effect boundary through `QuestionnaireSubmitSideEffectGateway`:

- `apply_tags` uses `WeComTagAdapter`.
- `emit_external_push` uses `QuestionnaireExternalPushAdapter`.
- `emit_automation_questionnaire_result` records the automation handoff through the gateway while preserving the existing internal fake automation boundary.
- `record_side_effect_audit` records skipped or internal-only side-effect decisions.

## Idempotency

Idempotency keys are derived from operation plus questionnaire id, submission id, external userid, tag ids, webhook target, OAuth state, or code hash. Repeated fake calls with the same idempotency key return the same deterministic fake result.

## Audit

D7.2 reuses the in-memory audit sink from D7.1. Each adapter call records `audit_id`, `adapter`, `operation`, `mode`, `idempotency_key`, `side_effect_executed`, `status`, `error_code`, and `created_at`. This is not a production audit database.

## API Compatibility

Existing admin questionnaire API, public H5 read/result API, fake submit response, and fake OAuth response shapes remain compatible. Adapter metadata is additive on submit responses and internal adapter calls; the OAuth callback response shape remains stable for existing clients.

## Side-Effect Safety

| side_effect | D7.2 status |
| --- | --- |
| real OAuth executed | false |
| real WeCom tag executed | false |
| real external webhook executed | false |
| production credential read | false |
| production traffic cutover | false |

## Rollback

Rollback is code-only: revert the D7.2 PR to restore previous direct fake submit/OAuth behavior. No production config, OAuth provider state, WeCom tag state, webhook target, or deploy setting is changed by this slice.

## Next Steps

After D7.2 acceptance, design staging fixtures for OAuth callback replay, WeCom tag allowlists, webhook retry/dead-letter behavior, and production evidence collection. Real external execution remains blocked pending explicit implementation, evidence, and human approval.
