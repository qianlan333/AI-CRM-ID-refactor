# D7 Write / External Replacement Plan

## A. D7 Goal

D7 turns the remaining write, external, and runtime blocker matrix into executable replacement batches.

D7 does not delete legacy code. D7 does not enable production outbound calls. D7 does not cut production traffic. D7 does not execute real write endpoints. It defines the contracts, modes, tests, canaries, and rollback gates required before any later implementation can replace legacy fallback code.

D8 legacy Flask shell retirement stays blocked until D7 replacements have fake, staging, and approved production evidence plus rollback proof.

## B. D7 Batches

| batch | scope | legacy_files | next_context | fake_mode | staging_mode | production_mode | required_tests | required_canary | rollback_strategy | delete_gate | risk_level |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D7.1 | Media storage and WeCom media adapter contract | `wecom_ability_service/domains/image_library`; `wecom_ability_service/domains/miniprogram_library`; `wecom_ability_service/domains/attachment_library`; `wecom_ability_service/http/cloud_orchestrator_campaign_details.py` | `aicrm_next.media_library`; `aicrm_next.integration_gateway` | return deterministic fake upload ids and never call cloud or WeCom | use staging buckets and sandbox WeCom credentials only with explicit staging flags | require explicit env flags for cloud and WeCom media adapter enablement | contract unit tests, size/type limit tests, idempotency tests, fake adapter smoke | readonly plus fake-write canary first; staging upload canary only after human approval | disable adapter flags and fall back to legacy media helpers | old media external fallback can be removed only after approved production evidence and rollback proof | high |
| D7.2 | Questionnaire submit, OAuth, WeCom tag, and external push | `wecom_ability_service/http/public_questionnaires.py`; `public_questionnaire_oauth.py`; `admin_questionnaires.py`; `admin_questionnaire_push_logs.py`; `wecom_ability_service/domains/questionnaire/` | `aicrm_next.questionnaire`; `aicrm_next.integration_gateway` | fake submit persists only to isolated fixture store and fake OAuth returns signed test identity | staging submit/OAuth/external push use sandbox callback targets and disabled real tag write by default | require explicit flags for submit write, OAuth callback, tag write, and webhook delivery | validation, duplicate submit, OAuth redirect, tag fake, webhook retry, idempotency tests | staged public submit canary without real external push, then adapter-specific canary | disable Next submit/OAuth/external flags and route back to legacy fallback | legacy questionnaire fallback removal requires production submit/OAuth/external evidence | critical |
| D7.3 | User Ops DND, batch-send, and WeCom dispatch | `wecom_ability_service/domains/user_ops/page_service.py`; `service.py`; `user_ops_deferred_job_service.py`; `wecom_ability_service/http/tasks.py`; `admin_jobs.py` | `aicrm_next.ops_enrollment`; `aicrm_next.integration_gateway` | fake DND and fake dispatch create audit rows only | staging dispatch uses allowlist recipients and dry-run queues by default | require explicit flags for DND writes, batch execute, deferred jobs, and WeCom dispatch | preview parity, fake execute, queue lease, audit, no-dispatch safety tests | batch-send preview canary, then allowlist dispatch canary | disable dispatch flags, stop workers, and use legacy fallback queues | delete old User Ops write fallback only after production dispatch evidence | critical |
| D7.4 | Product writes, WeChat Pay, and Alipay | `wecom_ability_service/http/wechat_pay.py`; `alipay_pay.py`; `admin_wechat_pay.py`; `admin_alipay_pay.py` | `aicrm_next.commerce`; `aicrm_next.integration_gateway` | fake product writes and fake payment session ids only | provider sandbox payment, notify, return, and reconciliation callbacks | require explicit provider env flags, credential checks, signature verification, and replay protection | product write validation, payment signing, notify idempotency, reconciliation tests | small sandbox and then human-approved low-risk payment canary | disable payment flags and route payment back to legacy provider | payment fallback removal requires signed provider evidence and reconciliation proof | critical |
| D7.5 | Automation writes, OpenClaw, and workflow runtime | `wecom_ability_service/http/automation_conversion*.py`; `customer_automation.py`; `wecom_ability_service/domains/automation_conversion/`; `openclaw_service/` | `aicrm_next.automation_engine`; `aicrm_next.integration_gateway` | fake state transitions, fake OpenClaw push, fake workflow execution | staging workflow executes against allowlisted members and fake external dispatch unless enabled | require explicit flags for manual override, confirm, webhook, OpenClaw, workflow, agent, and WeCom dispatch | state machine, command idempotency, webhook signature, workflow dry-run, OpenClaw fake tests | command-only canary first; runtime canary after external owner approval | disable runtime flags, stop workers, and use legacy automation fallback | old automation fallback removal requires production runtime evidence | critical |
| D7.6 | Archive sync, contacts sync, and identity mapping | `wecom_ability_service/http/archive.py`; `contacts.py`; `identity.py`; customer dependency fallback packages | `aicrm_next.customer_read_model`; `aicrm_next.identity_contact`; `aicrm_next.integration_gateway` | fake sync imports fixture contacts/messages into isolated tables | staging sync uses sandbox or read-only shadow credentials | require explicit sync and identity mapping flags plus cursor guard | cursor, dedupe, no-leak, identity merge, shadow parity tests | shadow sync canary with no overwrite first | disable sync flags and rely on legacy archive/contacts/identity fallback | old sync fallback removal requires production shadow and reconciliation evidence | critical |
| D7.7 | MCP and OpenClaw legacy adapter retirement | `wecom_ability_service/mcp_adapter.py`; `openclaw_service/` | `aicrm_next.integration_gateway`; future MCP adapter boundary | fake tool execution returns deterministic tool envelopes | staging tool execution uses allowlisted skills and audit-only side effects | require explicit MCP/OpenClaw adapter flags, allowlist, and audit | tool schema, permission, allowlist, fake execution, timeout tests | staging MCP allowlist canary | disable adapter flags and keep legacy MCP/OpenClaw fallback | old adapter removal requires approved integration canary | critical |

## C. Recommended Priority

1. D7.1 Media storage / WeCom media adapter contract.
2. D7.2 Questionnaire submit / OAuth / WeCom tag.
3. D7.3 User Ops DND / batch-send fake-to-real boundary.
4. D7.6 Archive / contacts / identity sync.
5. D7.5 Automation write / OpenClaw runtime.
6. D7.4 Payment last.
7. D7.7 MCP / OpenClaw adapter retirement after the OpenClaw and automation boundary is proven.

Payment is last because it is the highest-risk path: money movement, notify idempotency, signature verification, reconciliation, refund or support workflows, and provider credential safety all require stronger evidence than readonly or fake-write routes.

## Non-Goals

- No production route flag changes.
- No production Nginx or deploy configuration changes.
- No real WeCom, OAuth, Payment, OpenClaw, or cloud call.
- No legacy write fallback deletion.
- No production approval claim.
