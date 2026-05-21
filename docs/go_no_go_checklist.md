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

## D8.5 Legacy DB / Maintenance Command Planning

| check | status | evidence |
| --- | --- | --- |
| Command inventory exists | PASS | `docs/d8_5_legacy_db_maintenance_command_inventory.md` |
| Retirement plan exists | PASS | `docs/d8_5_legacy_db_maintenance_command_retirement_plan.md` |
| Replacement matrix exists | PASS | `docs/d8_5_maintenance_command_replacement_matrix.md` |
| Readiness checker exists | PASS | `tools/check_d8_5_legacy_maintenance_command_readiness.py` |
| Targeted tests exist | PASS | `tests/test_d8_5_legacy_maintenance_command_readiness.py` |
| Legacy commands retained | PASS | `app.py`, `legacy_flask_app.py`, legacy DB helpers, and old maintenance helpers remain in place |
| Production DB migration executed | NO | planning only |
| Production config modified | NO | no deploy, production, nginx, or systemd change |
| Real traffic cutover | NO | planning only |
| External service call | NO | no WeCom, OAuth, Payment, OpenClaw, cloud, or MCP external call |

D8.5 can proceed to acceptance after the D8.5 checker, targeted tests, legacy smoke, and D8.4 checker regression pass.

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

## D8 Legacy Flask Shell Retirement Planning

| item | status | evidence |
| --- | --- | --- |
| D8 retirement plan exists | PASS | `docs/d8_legacy_flask_shell_retirement_plan.md` |
| D8 dependency inventory exists | PASS | `docs/d8_legacy_shell_dependency_inventory.md` |
| D8 allowed fallback matrix exists | PASS | `docs/d8_legacy_shell_allowed_fallback_matrix.md` |
| D8 readiness checker exists | PASS | `tools/check_d8_legacy_shell_retirement_readiness.py` |
| D8 targeted tests exist | PASS | `tests/test_d8_legacy_shell_retirement_readiness.py` |
| `app.py` default runtime | PASS | `python3 app.py run` remains AI-CRM Next |
| Legacy fallback retained | PASS | `legacy_flask_app.py` remains present |
| Legacy shell core retained | PASS | `wecom_ability_service/__init__.py`, `wecom_ability_service/routes.py`, and `wecom_ability_service/http/__init__.py` remain present |
| OpenClaw service retained | PASS | `openclaw_service/` remains present |
| Real external adapters enabled | NO | D8.0 planning only |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Real traffic cutover | NO | D8.0 planning only |
| Recommended next gate | PASS | D8 acceptance before D8.1 fallback route lockdown planning |

## D8.1 Legacy Fallback Route Lockdown Planning

| item | status | evidence |
| --- | --- | --- |
| D8.1 lockdown plan exists | PASS | `docs/d8_1_legacy_fallback_route_lockdown_plan.md` |
| D8.1 route matrix exists | PASS | `docs/d8_1_legacy_fallback_route_matrix.md` |
| D8.1 checker exists | PASS | `tools/check_d8_1_legacy_fallback_route_lockdown.py` |
| D8.1 targeted tests exist | PASS | `tests/test_d8_1_legacy_fallback_route_lockdown.py` |
| D1-D6 retired readonly route matrix | PASS | Media, Product, Customer, User Ops, Questionnaire, and Automation readonly owner routes are listed as `retired_readonly_route` |
| Allowed fallback registry | PASS | legacy CLI fallback, write/external fallback, payment, OAuth, archive/contact sync, OpenClaw, and diagnostics are documented as fallback only |
| Runtime enforcement | NO | D8.1 planning/checker only; D8.2 is future enforcement implementation |
| Legacy shell deletion | NO | `legacy_flask_app.py`, `wecom_ability_service/`, and `openclaw_service/` remain retained |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Real traffic cutover | NO | D8.1 planning only |
| Recommended next gate | PASS | D8.1 acceptance before D8.2 enforcement planning |

## D8.2 Legacy Fallback Route Lockdown Enforcement

| item | status | evidence |
| --- | --- | --- |
| D8.2 enforcement design exists | PASS | `docs/d8_2_legacy_fallback_route_lockdown_enforcement.md` |
| D8.2 implementation report exists | PASS | `docs/d8_2_legacy_fallback_route_lockdown_report.md` |
| Legacy lockdown module exists | PASS | `wecom_ability_service/legacy_lockdown.py` |
| Legacy app factory registration | PASS | `register_legacy_lockdown(app)` is wired in `wecom_ability_service/__init__.py` |
| D8.2 checker exists | PASS | `tools/check_d8_2_legacy_lockdown_enforcement.py` |
| D8.2 targeted tests exist | PASS | `tests/test_d8_2_legacy_lockdown_enforcement.py` |
| Retired readonly route behavior | PASS | legacy fallback returns 410 retired response for D1-D6 readonly owner routes |
| Allowed fallback behavior | PASS | payment, OAuth, archive/contact sync, OpenClaw, questionnaire submit, and diagnostics are not blocked by the lockdown guard |
| Legacy shell deletion | NO | `legacy_flask_app.py`, `wecom_ability_service/`, and `openclaw_service/` remain retained |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Real traffic cutover | NO | D8.2 only affects explicit legacy fallback runtime |
| Real external calls | NO | no WeCom, OAuth, Payment, OpenClaw, cloud, or webhook calls are executed |
| Recommended next gate | PASS | D8.2 acceptance before D8.3 legacy archive package planning |

## D8.3 Legacy Flask Archive Package Move Planning

| item | status | evidence |
| --- | --- | --- |
| D8.3 archive package plan exists | PASS | `docs/d8_3_legacy_flask_shell_archive_package_plan.md` |
| D8.3 move map exists | PASS | `docs/d8_3_legacy_package_move_map.md` |
| D8.3 import rewrite plan exists | PASS | `docs/d8_3_legacy_import_rewrite_plan.md` |
| D8.3 checker exists | PASS | `tools/check_d8_3_legacy_archive_move_readiness.py` |
| D8.3 targeted tests exist | PASS | `tests/test_d8_3_legacy_archive_move_readiness.py` |
| Physical package move | NO | `wecom_ability_service/` remains in place |
| OpenClaw package move | NO | `openclaw_service/` remains in place |
| `legacy_flask/` package created | NO | D8.3.0 is planning only |
| Default runtime | PASS | `python3 app.py run` remains AI-CRM Next |
| D8.2 lockdown regression | PASS | D8.2 checker remains the move gate baseline |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Real traffic cutover | NO | D8.3 planning only |
| Real external calls | NO | no WeCom, OAuth, Payment, OpenClaw, cloud, or webhook calls are executed |
| Recommended next gate | PASS | D8.3 acceptance before D8.3.1 archive package skeleton work |

## D8.4 Legacy Flask Archive Package Implementation

| item | status | evidence |
| --- | --- | --- |
| `legacy_flask/` package exists | PASS | `legacy_flask/__init__.py`, `legacy_flask/app_factory.py`, `legacy_flask/http/__init__.py`, `legacy_flask/legacy_lockdown.py` |
| Compatibility shims exist | PASS | `wecom_ability_service/__init__.py`, `routes.py`, `http/__init__.py`, and `legacy_lockdown.py` |
| `legacy_flask_app.py` imports archive app factory | PASS | explicit fallback uses `legacy_flask.app_factory` |
| `app.py` default runtime | PASS | default run remains AI-CRM Next |
| D8.4 checker exists | PASS | `tools/check_d8_4_legacy_archive_package.py` |
| D8.4 targeted tests exist | PASS | `tests/test_d8_4_legacy_archive_package.py` |
| D8.2 lockdown regression | PASS | retired readonly route still returns 410 and allowed diagnostic route is not blocked |
| OpenClaw service retained | PASS | `openclaw_service/` remains in place |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Real traffic cutover | NO | explicit legacy fallback only |
| Real external calls | NO | no WeCom, OAuth, Payment, OpenClaw, cloud, or webhook calls are executed |
| Recommended next gate | PASS | D8.4 acceptance before D8.5 removal planning |
