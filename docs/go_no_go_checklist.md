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

## D8.2 Legacy Fallback Route Lockdown Preflight

| check | status | evidence |
| --- | --- | --- |
| D8.2 preflight doc exists | PASS | `docs/d8_2_legacy_fallback_route_lockdown_preflight.md` |
| D8.2 preflight checker exists | PASS | `tools/check_d8_2_legacy_lockdown_preflight.py` |
| Targeted tests exist | PASS | `tests/test_d8_2_legacy_lockdown_preflight.py` |
| Runtime lockdown guard created | NO | preflight only |
| `legacy_flask/` package created | NO | current main has no archive package |
| Legacy fallback retained | PASS | `legacy_flask_app.py` and `wecom_ability_service/` remain in place |
| Production config modified | NO | no deploy, production, nginx, or systemd change |
| Real traffic cutover | NO | preflight only |
| External service call | NO | no WeCom, OAuth, Payment, OpenClaw, cloud, or MCP external call |

D8.2 preflight can proceed to acceptance after the D8.2 checker, targeted tests, legacy smoke, and D8.0/D8.1 checker regressions pass. Runtime enforcement requires a later approved phase.

## D9 OpenClaw Legacy Adapter Physical Retirement Planning

| check | status | evidence |
| --- | --- | --- |
| D9 retirement plan exists | PASS | `docs/d9_openclaw_legacy_adapter_retirement_plan.md` |
| D9 dependency inventory exists | PASS | `docs/d9_openclaw_legacy_dependency_inventory.md` |
| D9 compatibility matrix exists | PASS | `docs/d9_openclaw_mcp_compatibility_matrix.md` |
| Readiness checker exists | PASS | `tools/check_d9_openclaw_legacy_retirement_readiness.py` |
| Targeted tests exist | PASS | `tests/test_d9_openclaw_legacy_retirement_readiness.py` |
| OpenClaw repo path status | PASS | D9.0 planning artifacts are historical; D9.6 records `openclaw_service/` as absent from the repo |
| Default Next import of OpenClaw service | NO | checker scans `aicrm_next` for direct old-package imports |
| Physical move/removal | NO | D9.0 planning only |
| Production config modified | NO | no deploy, production, nginx, or systemd change |
| Real traffic cutover | NO | planning only |
| External service call | NO | no OpenClaw, MCP external, webhook, WeCom, OAuth, Payment, or cloud call |

D9 can proceed to acceptance after the D9 checker, targeted tests, legacy/Next smoke, and D7.7 checker regression pass.

## D9.1 OpenClaw Legacy Import Freeze

| check | status | evidence |
| --- | --- | --- |
| Import freeze plan exists | PASS | `docs/d9_1_openclaw_legacy_import_freeze_plan.md` |
| Import allowlist exists | PASS | `docs/d9_1_openclaw_import_allowlist.md` |
| Import freeze checker exists | PASS | `tools/check_d9_1_openclaw_import_freeze.py` |
| Targeted tests exist | PASS | `tests/test_d9_1_openclaw_import_freeze.py` |
| OpenClaw repo path status | PASS | D9.1 import-freeze artifacts are historical; D9.6 records `openclaw_service/` as absent from the repo |
| AI-CRM Next runtime import | NO | checker blocks `aicrm_next/**` imports of `openclaw_service` |
| Physical move/removal | NO | D9.1 freeze only |
| Production config modified | NO | no deploy, production, nginx, or systemd change |
| Real traffic cutover | NO | freeze only |
| External service call | NO | no OpenClaw, MCP external, webhook, WeCom, OAuth, Payment, or cloud call |

D9.1 can proceed to acceptance after the D9.1 checker, targeted tests, app/legacy smoke, and D9 checker regression pass.

## D9.2 OpenClaw Legacy Move Planning

| check | status | evidence |
| --- | --- | --- |
| Move plan exists | PASS | `docs/d9_2_openclaw_legacy_move_plan.md` |
| Move map exists | PASS | `docs/d9_2_openclaw_legacy_move_map.md` |
| Import rewrite plan exists | PASS | `docs/d9_2_openclaw_import_rewrite_plan.md` |
| Readiness checker exists | PASS | `tools/check_d9_2_openclaw_legacy_move_readiness.py` |
| Targeted tests exist | PASS | `tests/test_d9_2_openclaw_legacy_move_readiness.py` |
| OpenClaw repo path status | PASS | D9.2 move-planning artifacts are historical; D9.6 records `openclaw_service/` as absent from the repo |
| Archive runtime package created | NO | `legacy_flask/openclaw_legacy/` is absent in D9.2 planning |
| AI-CRM Next runtime import | NO | D9.1/D9.2 checkers block `aicrm_next/**` imports of `openclaw_service` |
| Physical move/removal | NO | D9.2 planning only |
| Production config modified | NO | no deploy, production, nginx, or systemd change |
| Real traffic cutover | NO | planning only |
| External service call | NO | no OpenClaw, MCP external, webhook, WeCom, OAuth, Payment, or cloud call |

D9.2 can proceed to acceptance after the D9.2 checker, targeted tests, app/legacy smoke, and D9.1 checker regression pass.

## D9.3 OpenClaw Legacy Archive Skeleton

| check | status | evidence |
| --- | --- | --- |
| Skeleton package exists | PASS | `legacy_flask/openclaw_legacy/` |
| Skeleton metadata exists | PASS | `legacy_flask/openclaw_legacy/__init__.py` |
| Skeleton docs exist | PASS | `README.md`, `LEGACY_FROZEN.md`, `MOVE_PENDING.md` |
| Implementation report exists | PASS | `docs/d9_3_openclaw_legacy_skeleton_implementation_report.md` |
| Readiness checker exists | PASS | `tools/check_d9_3_openclaw_legacy_skeleton.py` |
| Targeted tests exist | PASS | `tests/test_d9_3_openclaw_legacy_skeleton.py` |
| OpenClaw repo path status | PASS | D9.3 skeleton artifacts are historical; D9.6 records `openclaw_service/` and `legacy_flask/openclaw_legacy/` as absent from the repo |
| Compatibility shim created | NO | no `openclaw_service/__init__.py` shim |
| Physical move/removal | NO | D9.3 skeleton only |
| Production config modified | NO | no deploy, production, nginx, or systemd change |
| Real traffic cutover | NO | skeleton only |
| External service call | NO | no OpenClaw, MCP external, webhook, WeCom, OAuth, Payment, or cloud call |

D9.3 can proceed to acceptance after the D9.3 checker, targeted tests, app/legacy smoke, and D9.1/D9.2 checker regressions pass.

## D9.4 OpenClaw Legacy Move With Shim

| item | status | evidence |
| --- | --- | --- |
| Archive package exists | PASS | `legacy_flask/openclaw_legacy/` |
| Frozen marker archived | PASS | `legacy_flask/openclaw_legacy/LEGACY_FROZEN.md` |
| Compatibility shim status | PASS | D9.4 shim artifacts are historical; D9.6 records the repo-side shim path as absent |
| AI-CRM Next direct old-package import | NO | D9.4 checker scans `aicrm_next/**` |
| Runtime owner change | NO | D7.7 adapter boundary remains primary |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Traffic cutover | NO | no runtime traffic change |
| External service call | NO | no OpenClaw, MCP external, webhook, WeCom, OAuth, Payment, or cloud call |
| Recommended next gate | PASS | D9.5 shim-removal planning after evidence and signoff |

## D9.5 OpenClaw Shim Removal Planning

| item | status | evidence |
| --- | --- | --- |
| Shim-removal plan exists | PASS | `docs/d9_5_openclaw_service_shim_removal_plan.md` |
| Final reference scan plan exists | PASS | `docs/d9_5_openclaw_final_reference_scan_plan.md` |
| Readiness checklist exists | PASS | `docs/d9_5_openclaw_shim_removal_readiness_checklist.md` |
| Compatibility shim status | PASS | D9.5 shim-removal planning is historical; D9.6 records the repo-side shim path as absent |
| Archive package status | PASS | D9.6 records `legacy_flask/openclaw_legacy/` as absent |
| AI-CRM Next direct old-package import | NO | D9.5 checker scans `aicrm_next/**` |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Traffic cutover | NO | planning only |
| External service call | NO | no OpenClaw, MCP external, webhook, WeCom, OAuth, Payment, or cloud call |
| Recommended next gate | PASS | D9.5.1 final reference scan and observation evidence capture |

## D9.5.1 OpenClaw Final Reference Scan Evidence

| item | status | evidence |
| --- | --- | --- |
| Final reference scan evidence exists | PASS | `docs/d9_5_1_openclaw_final_reference_scan_evidence.md` |
| Observation evidence report exists | PASS | `docs/d9_5_1_openclaw_observation_evidence_report.md` |
| Deletion readiness evidence matrix exists | PASS | `docs/d9_5_1_openclaw_shim_deletion_readiness_evidence_matrix.md` |
| Compatibility shim status | PASS | D9.5.1 evidence is historical; D9.6 records the repo-side shim path as absent |
| AI-CRM Next direct old-package import | NO | AST scan reports zero imports |
| Experiments mirror direct old-package import | NO | AST scan reports zero imports |
| Deploy/script reference | NO | targeted `deploy/`, `.github/`, and `scripts/` scans report zero hits |
| Observation window evidence | PENDING | production/runtime logs are not available in this local environment |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Traffic cutover | NO | evidence capture only |
| External service call | NO | no OpenClaw, MCP external, webhook, WeCom, OAuth, Payment, or cloud call |
| Recommended next gate | PASS | D9.5.1 acceptance; deletion proposal still requires observation evidence, rollback independence, and signoff |

## D9.5.2 OpenClaw Shim Deletion Blocked Package

| item | status | evidence |
| --- | --- | --- |
| Deletion blocked summary exists | PASS | `docs/d9_5_2_openclaw_shim_deletion_blocked_summary.md` |
| Observation collection runbook exists | PASS | `docs/d9_5_2_openclaw_observation_collection_runbook.md` |
| Deletion PR preflight checklist exists | PASS | `docs/d9_5_2_openclaw_deletion_pr_preflight_checklist.md` |
| Compatibility shim status | PASS | D9.5.2 blocked package is historical; D9.6 records the repo-side shim path as absent |
| Deletion candidate | NO | blocked until production observation evidence exists |
| AI-CRM Next direct old-package import | NO | checker scans `aicrm_next/**` |
| Observation evidence | PENDING | production/runtime logs are not available in this local environment |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Traffic cutover | NO | blocked-status package only |
| External service call | NO | no OpenClaw, MCP external, webhook, WeCom, OAuth, Payment, or cloud call |
| Recommended next gate | PASS | pause for observation evidence before any deletion PR |

## D9.6 OpenClaw Shim Physical Deletion

| item | status | evidence |
| --- | --- | --- |
| Physical deletion report exists | PASS | `docs/d9_6_openclaw_physical_deletion_report.md` |
| Repository shim path removed | PASS | `openclaw_service/` absent |
| Repository archive path removed | PASS | `legacy_flask/openclaw_legacy/` absent |
| Server OpenClaw-named jobs backed up | PASS | `/home/ubuntu/backups/openclaw-retirement-20260522004443` |
| Server OpenClaw-named cron/timer jobs removed | PASS | user crontab empty; two OpenClaw timers/services removed; `/etc/cron.d/openclaw-campaign-run-due` removed |
| Database/environment service retained | PASS | `openclaw-wecom-postgres.service` retained intentionally |
| AI-CRM Next direct old-package import | NO | D9.6 checker scans Next runtime source |
| Production nginx/app restart | NO | no nginx or app process restart performed |
| External service call | NO | no OpenClaw or MCP external call performed |

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
| OpenClaw legacy bridge gate | PASS | Automation OpenClaw fake push records D7.7 bridge metadata; D9.6 records `openclaw_service/` as absent and no reintroduction is allowed |
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
| OpenClaw repo path status | PASS | `openclaw_service/` is absent after D9.6 and is not part of D8 legacy shell fallback |
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
| Legacy shell deletion | NO | `legacy_flask_app.py` and `wecom_ability_service/` remain retained; `openclaw_service/` is absent after D9.6 |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Real traffic cutover | NO | D8.1 planning only |
| Recommended next gate | PASS | D8.1 acceptance before D8.2 enforcement planning |

## D8.2 Legacy Fallback Route Lockdown Preflight

| item | status | evidence |
| --- | --- | --- |
| D8.2 preflight doc exists | PASS | `docs/d8_2_legacy_fallback_route_lockdown_preflight.md` |
| D8.2 preflight checker exists | PASS | `tools/check_d8_2_legacy_lockdown_preflight.py` |
| D8.2 targeted tests exist | PASS | `tests/test_d8_2_legacy_lockdown_preflight.py` |
| Runtime lockdown module | NO | no `wecom_ability_service/legacy_lockdown.py` runtime guard is introduced by preflight |
| Retired readonly route behavior | NO | preflight only; no runtime 410 behavior is registered |
| Allowed fallback behavior | PASS | payment, OAuth, archive/contact sync, OpenClaw/MCP fake adapter boundary, questionnaire submit, and diagnostics remain documented fallback categories |
| Legacy shell deletion | NO | `legacy_flask_app.py` and `wecom_ability_service/` remain retained; `openclaw_service/` is absent after D9.6 |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Real traffic cutover | NO | preflight only |
| Real external calls | NO | no WeCom, OAuth, Payment, OpenClaw, cloud, or webhook calls are executed |
| Recommended next gate | PASS | D8.2 preflight acceptance before any separate runtime-enforcement proposal |

## D8.3 Legacy Flask Archive Package Move Planning

| item | status | evidence |
| --- | --- | --- |
| D8.3 archive package plan exists | NO | not restored on current main |
| D8.3 checker exists | NO | not restored on current main |
| D8.3 targeted tests exist | NO | not restored on current main |
| Physical package move | NO | `wecom_ability_service/` remains in place |
| OpenClaw package move | NO | D9.6 records `openclaw_service/` as absent; D8 must not reintroduce it |
| `legacy_flask/` package created | NO | current main has no archive package |
| Default runtime | PASS | `python3 app.py run` remains AI-CRM Next |
| D8.2 preflight regression | PASS | D8.2 preflight checker remains the gate baseline |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Real traffic cutover | NO | D8.3 planning only |
| Real external calls | NO | no WeCom, OAuth, Payment, OpenClaw, cloud, or webhook calls are executed |
| Recommended next gate | PASS | no D8.3 work until separately approved |

## D8.4 Legacy Flask Archive Package Implementation

| item | status | evidence |
| --- | --- | --- |
| `legacy_flask/` package exists | NO | not present on current main |
| Compatibility shims exist | PASS | `wecom_ability_service/__init__.py`, `routes.py`, and `http/__init__.py` remain legacy fallback entry points |
| `legacy_flask_app.py` imports archive app factory | NO | explicit fallback remains on the current legacy app entry |
| `app.py` default runtime | PASS | default run remains AI-CRM Next |
| D8.4 checker exists | NO | not present on current main |
| D8.4 targeted tests exist | NO | not present on current main |
| D8.2 lockdown regression | NO | no runtime lockdown is registered by D8.2 preflight |
| OpenClaw repo path status | PASS | `openclaw_service/` is absent after D9.6 and must not be restored |
| Production config modified | NO | no deploy/nginx/systemd changes |
| Real traffic cutover | NO | no D8.4 implementation on current main |
| Real external calls | NO | no WeCom, OAuth, Payment, OpenClaw, cloud, or webhook calls are executed |
| Recommended next gate | PASS | no D8.4 work until separately approved |
