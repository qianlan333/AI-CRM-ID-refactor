# D7.2 Questionnaire Adapter Implementation Report

## Goal

Move Questionnaire submit, OAuth, WeCom tag, and external push fake behavior behind formal integration gateway adapter contracts. This report covers implementation only; it does not authorize real OAuth, WeCom tag writes, external webhook delivery, production route changes, or legacy fallback deletion.

## Implementation Summary

| area | result |
| --- | --- |
| WeChatOAuthAdapter contract | implemented in `aicrm_next/integration_gateway/questionnaire_adapters.py` |
| WeComTagAdapter contract | implemented in `aicrm_next/integration_gateway/questionnaire_adapters.py` |
| QuestionnaireExternalPushAdapter contract | implemented in `aicrm_next/integration_gateway/questionnaire_adapters.py` |
| QuestionnaireSubmitSideEffectGateway | implemented in `aicrm_next/integration_gateway/questionnaire_adapters.py` |
| Contract protocols | implemented in `aicrm_next/integration_gateway/questionnaire_contracts.py` |
| Idempotency guard | reused from `aicrm_next/integration_gateway/idempotency.py` |
| In-memory audit log | reused from `aicrm_next/integration_gateway/audit.py` |
| Questionnaire integration | submit side effects and OAuth start/callback now route through integration gateway adapters |
| Production real calls | not implemented and not executed |

## Actual Behavior

| mode | result |
| --- | --- |
| fake | deterministic fake OAuth identity, fake tag operation, and fake push result |
| disabled | stable disabled error |
| staging | staging-shaped fake record; no outbound call |
| production without explicit flag | fail closed |
| production with explicit flag | `production_not_implemented`; no outbound call |

## API Compatibility

The existing readonly questionnaire APIs and fake submit contract continue to satisfy parity. OAuth start/callback keep the existing client-facing fields. Submit responses add side-effect safety and adapter boundary evidence without removing existing fields.

## Safety Summary

| check | status |
| --- | --- |
| real OAuth executed | false |
| real WeCom tag executed | false |
| real external webhook executed | false |
| production credentials read | false |
| production config modified | false |
| production traffic cutover | false |
| old system write endpoint executed | false |

## Reference Scan Summary

The implementation is contained in `aicrm_next/integration_gateway` and `aicrm_next/questionnaire`. It does not import `wecom_ability_service` or `openclaw_service`. Legacy questionnaire submit/OAuth/external fallback remains protected by the D7 blocker matrix and is not removed in this slice.

## Validation Plan

| validation | command |
| --- | --- |
| D7.2 checker | `python3 tools/check_d7_2_questionnaire_adapter_contract.py --output-md /tmp/d7_2_questionnaire_adapter_contract.md --output-json /tmp/d7_2_questionnaire_adapter_contract.json` |
| tests | `python3 -m pytest -q` or available project venv |
| questionnaire smoke | `.venv/bin/python tools/questionnaire_readonly_gray_smoke.py --next-testclient --include-fake-submit --output-md /tmp/questionnaire_smoke_after_d7_2.md --output-json /tmp/questionnaire_smoke_after_d7_2.json` |
| questionnaire parity | `.venv/bin/python tools/compare_questionnaire_parity.py --old-fixture-dir experiments/ai_crm_next/tests/fixtures/old_questionnaire --next-testclient --output-md /tmp/questionnaire_parity_after_d7_2.md --output-json /tmp/questionnaire_parity_after_d7_2.json` |

## Risks

| risk | mitigation |
| --- | --- |
| submit response drift | adapter metadata is additive and required parity fields remain present |
| accidental external OAuth/tag/webhook | no HTTP client, WeCom SDK, provider SDK, or webhook client is used by D7.2 adapters |
| production mode confusion | production mode fails closed and still has no real-call implementation |

## Rollback

Revert the D7.2 PR. Because no production config, OAuth state, WeCom tag state, webhook delivery, credentials, or production traffic is changed, rollback does not require external cleanup.

## Remaining D7 Blockers

Questionnaire submit, OAuth, WeCom tag, and external push have fake contracts only. Real provider integration, staging evidence, production canary evidence, rollback proof, and human approval remain required before old external fallback can be retired.
