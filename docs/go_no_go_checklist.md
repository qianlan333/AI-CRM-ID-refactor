# Go / No-Go Checklist

## D6.5 Dead Legacy Cleanup

| check | status | evidence |
| --- | --- | --- |
| Dead legacy inventory exists | PASS | `docs/legacy_dead_code_inventory.md` |
| Cleanup report exists | PASS | `docs/legacy_d6_5_dead_cleanup_report.md` |
| D7 blocker matrix exists | PASS | `docs/d7_write_external_blocker_matrix.md` |
| Checker exists | PASS | `tools/check_legacy_dead_cleanup.py` |
| Checker tests exist | PASS | `tests/test_legacy_dead_cleanup.py` |
| Actual deletion happened | PASS | orphan attachment template and stale generated route inventory removed |
| Protected fallback kept | PASS | write/external/runtime blocker matrix and checker protected files |
| Production config modified | NO | no deploy, production, nginx, systemd, or supervisor config change |
| Real traffic cutover | NO | cleanup only |
| External service call | NO | no WeCom, OAuth, Payment, OpenClaw, or cloud call |
| Old write endpoint executed | NO | no write smoke executed |
| Next write endpoint executed | NO | readonly parity and tests only |

## Go / No-Go

D6.5 can proceed to acceptance only after checker, fallback smoke, pytest, and six parity checks pass. D7 remains blocked until replacement plans and production evidence exist.

## D7 Replacement Planning

| check | status | evidence |
| --- | --- | --- |
| D7 replacement master plan exists | PASS | `docs/d7_write_external_replacement_plan.md` |
| D7 adapter contract catalog exists | PASS | `docs/d7_adapter_contract_catalog.md` |
| D7 capability readiness matrix exists | PASS | `docs/d7_capability_readiness_matrix.md` |
| D7 planning checker exists | PASS | `tools/check_d7_replacement_planning.py` |
| Recommended first batch | PASS | D7.1 Media storage / WeCom media adapter contract |
| Real external call | NO | planning only |
| Production route change | NO | planning only |
| Legacy write/external deletion | NO | planning only |

## D7.1 Media Adapter Contract

| item | status | evidence |
| --- | --- | --- |
| CloudStorageAdapter fake contract | PASS | `aicrm_next/integration_gateway/media_adapters.py` |
| WeComMediaAdapter fake contract | PASS | `aicrm_next/integration_gateway/media_adapters.py` |
| Idempotency guard | PASS | `aicrm_next/integration_gateway/idempotency.py` |
| In-memory audit boundary | PASS | `aicrm_next/integration_gateway/audit.py` |
| Production external calls | NO | production mode fails closed or returns not implemented |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Recommended next gate | PASS | D7.1 acceptance before any staging/provider work |

## D7.2 Questionnaire Adapter Contract

| item | status | evidence |
| --- | --- | --- |
| WeChatOAuthAdapter fake contract | PASS | `aicrm_next/integration_gateway/questionnaire_adapters.py` |
| WeComTagAdapter fake contract | PASS | `aicrm_next/integration_gateway/questionnaire_adapters.py` |
| QuestionnaireExternalPushAdapter fake contract | PASS | `aicrm_next/integration_gateway/questionnaire_adapters.py` |
| Submit side-effect gateway | PASS | `aicrm_next/integration_gateway/questionnaire_adapters.py` |
| Idempotency guard | PASS | `aicrm_next/integration_gateway/idempotency.py` |
| In-memory audit boundary | PASS | `aicrm_next/integration_gateway/audit.py` |
| Production OAuth / tag / webhook calls | NO | production mode fails closed or returns not implemented |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Recommended next gate | PASS | D7.2 acceptance before any staging/provider work |

## D7.3 User Ops Adapter Contract

| item | status | evidence |
| --- | --- | --- |
| UserOpsDndWriteGateway fake contract | PASS | `aicrm_next/integration_gateway/user_ops_adapters.py` |
| UserOpsBatchSendGateway fake contract | PASS | `aicrm_next/integration_gateway/user_ops_adapters.py` |
| WeComMessageDispatchAdapter fake contract | PASS | `aicrm_next/integration_gateway/user_ops_adapters.py` |
| UserOpsDeferredJobGateway fake contract | PASS | `aicrm_next/integration_gateway/user_ops_adapters.py` |
| Idempotency guard | PASS | `aicrm_next/integration_gateway/idempotency.py` |
| In-memory audit boundary | PASS | `aicrm_next/integration_gateway/audit.py` |
| Real DND / batch-send / WeCom dispatch / deferred jobs | NO | production mode fails closed or returns not implemented |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Recommended next gate | PASS | D7.3 acceptance before any staging/provider work |

## D7.4 Product Payment Adapter Contract

| item | status | evidence |
| --- | --- | --- |
| ProductWriteGateway fake contract | PASS | `aicrm_next/integration_gateway/payment_adapters.py` |
| WeChatPayAdapter fake contract | PASS | `aicrm_next/integration_gateway/payment_adapters.py` |
| AlipayAdapter fake contract | PASS | `aicrm_next/integration_gateway/payment_adapters.py` |
| PaymentNotifyGateway fake contract | PASS | `aicrm_next/integration_gateway/payment_adapters.py` |
| PaymentReturnGateway fake contract | PASS | `aicrm_next/integration_gateway/payment_adapters.py` |
| Idempotency guard | PASS | `aicrm_next/integration_gateway/idempotency.py` |
| In-memory audit boundary | PASS | `aicrm_next/integration_gateway/audit.py` |
| Real product write / WeChat Pay / Alipay / notify | NO | production mode fails closed or returns not implemented |
| Production config modified | NO | no deploy/nginx/systemd changes |
| D7.1-D7.3 prerequisite status | PASS | accepted prerequisites, not part of the D7.4 current increment |
| Scope isolation checker | PASS | `tools/check_d7_scope_isolation.py` confirms D7.4 current increment classification |
| Recommended next gate | PASS | D7.4 scope isolation acceptance before any D7.5 or sandbox/provider work |

## D7.5 Automation / OpenClaw / Runtime Adapter Contract

| item | status | evidence |
| --- | --- | --- |
| AutomationWriteGateway fake contract | PASS | `aicrm_next/integration_gateway/automation_adapters.py` |
| AutomationActivationGateway fake contract | PASS | `aicrm_next/integration_gateway/automation_adapters.py` |
| OpenClawWebhookAdapter fake contract | PASS | `aicrm_next/integration_gateway/automation_adapters.py` |
| AutomationWorkflowRuntimeAdapter fake contract | PASS | `aicrm_next/integration_gateway/automation_adapters.py` |
| AutomationAgentRuntimeAdapter fake contract | PASS | `aicrm_next/integration_gateway/automation_adapters.py` |
| Automation application boundary | PASS | manual override, activation webhook, OpenClaw fake push, workflow wrapper, and agent wrapper use D7.5 adapters |
| Idempotency guard | PASS | `aicrm_next/integration_gateway/idempotency.py` |
| In-memory audit boundary | PASS | `aicrm_next/integration_gateway/audit.py` |
| Real automation write / activation webhook / OpenClaw / workflow / agent runtime | NO | production mode fails closed or returns not implemented |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Recommended next gate | PASS | D7.5 acceptance after checker, tests, Automation smoke, and Automation parity pass |

## D7.6 Archive / Contacts / Identity Adapter Contract

| item | status | evidence |
| --- | --- | --- |
| ArchiveSyncAdapter fake contract | PASS | `aicrm_next/integration_gateway/customer_sync_adapters.py` |
| ContactsSyncAdapter fake contract | PASS | `aicrm_next/integration_gateway/customer_sync_adapters.py` |
| IdentityMappingAdapter fake contract | PASS | `aicrm_next/integration_gateway/customer_sync_adapters.py` |
| CustomerProjectionSyncGateway fake contract | PASS | `aicrm_next/integration_gateway/customer_sync_adapters.py` |
| Customer / Identity application boundary | PASS | recent messages, contacts projection, identity resolve/upsert/link, and projection wrappers use D7.6 adapters |
| Idempotency guard | PASS | `aicrm_next/integration_gateway/idempotency.py` |
| In-memory audit boundary | PASS | `aicrm_next/integration_gateway/audit.py` |
| Real archive sync / contacts sync / identity write / projection write / WeCom call | NO | production mode fails closed or returns not implemented |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Recommended next gate | PASS | D7.6 acceptance after checker, tests, Customer smoke, and Customer parity pass |

## D7.7 MCP / OpenClaw Legacy Adapter Contract

| item | status | evidence |
| --- | --- | --- |
| McpToolGateway fake contract | PASS | `aicrm_next/integration_gateway/mcp_openclaw_adapters.py` |
| CustomerContextToolAdapter fake contract | PASS | `aicrm_next/integration_gateway/mcp_openclaw_adapters.py` |
| AutomationContextToolAdapter fake contract | PASS | `aicrm_next/integration_gateway/mcp_openclaw_adapters.py` |
| OpenClawLegacyBridgeAdapter fake contract | PASS | `aicrm_next/integration_gateway/mcp_openclaw_adapters.py` |
| McpCompatibilityGateway fake contract | PASS | `aicrm_next/integration_gateway/mcp_openclaw_adapters.py` |
| MCP / Customer / Automation boundary | PASS | MCP dispatcher routes tool, customer context, recent messages, automation context, and compatibility through D7.7 adapters |
| OpenClaw legacy bridge gate | PASS | Automation OpenClaw fake push records D7.7 bridge metadata; `openclaw_service/` remains retained |
| Idempotency guard | PASS | `aicrm_next/integration_gateway/idempotency.py` |
| In-memory audit boundary | PASS | `aicrm_next/integration_gateway/audit.py` |
| Real MCP external call / OpenClaw call / webhook | NO | production mode fails closed or returns not implemented |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Recommended next gate | PASS | D7.7 acceptance after checker, tests, Customer/Automation smoke, and Customer/Automation parity pass |
