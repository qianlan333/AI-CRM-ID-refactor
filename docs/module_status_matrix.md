# Module Status Matrix

This root matrix tracks the runtime-switch and legacy-retirement state. It does not mark any module as production approved or production ready.

| module | next_owner | readonly_status | legacy_status | write_external_status | current_gate | next_action |
| --- | --- | --- | --- | --- | --- | --- |
| Runtime | `aicrm_next.main` | default runtime | legacy Flask fallback retained | not applicable | D8.0 planning gate | keep fallback until D8 phased gates and production evidence clear |
| Media Library | `aicrm_next.media_library` | D1 retired old readonly owner | old media route modules removed; D6.5 removed orphan attachment template | CloudStorageAdapter and WeComMediaAdapter fake contracts accepted; real upload blocked | D7.1 accepted | provider evidence before real calls |
| Product Management | `aicrm_next.commerce` | D2 retired old readonly owner | admin product owner removed | product writes and payment contracts accepted fake; real provider behavior blocked | D7.4 accepted | sandbox/provider evidence before real calls |
| Customer Read Model | `aicrm_next.customer_read_model` | D3 retired old readonly owner | customer dependency fallback retained | archive, contacts, identity, projection fake contracts accepted | D7.6 accepted | sync/projection evidence before real calls |
| User Ops | `aicrm_next.ops_enrollment` | D4 retired old readonly owner | domain write/job fallback retained | DND, batch-send, deferred jobs, WeCom dispatch fake contracts accepted | D7.3 accepted | operator and dispatch evidence before real calls |
| Questionnaire | `aicrm_next.questionnaire` | D5 retired old readonly owner | mixed submit/write/OAuth/external fallback retained | submit, OAuth, WeCom tag, external push fake contracts accepted | D7.2 accepted | OAuth/tag/webhook evidence before real calls |
| Automation | `aicrm_next.automation_engine` | D6 retired old readonly owner | mixed write/external/runtime fallback retained | manual override, activation, OpenClaw, workflow, agent fake contracts accepted | D7.5 accepted | runtime and OpenClaw evidence before real calls |
| MCP / OpenClaw | `aicrm_next.integration_gateway` | context/tool reads via Next boundary | `openclaw_service/` retained | MCP/OpenClaw fake contracts accepted; real external calls blocked | D7.7 accepted | compatibility and token-policy evidence before real calls |
| D8 Legacy Shell | `aicrm_next.main` default plus explicit fallback | readonly owner migration already staged | `legacy_flask/` entry layer, `wecom_ability_service/` compatibility shim, `openclaw_service/`, and legacy maintenance commands retained | legacy fallback guard blocks retired readonly routes only; maintenance command retirement planning ready | maintenance_command_retirement_planning_ready | D8.5 acceptance before command removal or DB migration implementation planning |

Production traffic has not been cut by D8.5. Real external adapters remain disabled, production DB migration is not executed, and legacy deletion is not authorized.
