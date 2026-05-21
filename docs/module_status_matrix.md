# Module Status Matrix

This root matrix tracks the runtime-switch and legacy-retirement state. It does not mark any module as production approved or production ready.

| module | next_owner | readonly_status | legacy_status | write_external_status | current_gate | next_action |
| --- | --- | --- | --- | --- | --- | --- |
| Runtime | `aicrm_next.main` | default runtime | legacy Flask fallback retained | not applicable | runtime switch accepted | keep fallback until all D7 blockers clear |
| Media Library | `aicrm_next.media_library` | D1 retired old readonly owner | old media route modules removed; D6.5 removed orphan attachment template | cloud and WeCom media upload blocked | D6.5 cleanup completed | D7 media upload replacement planning |
| Product Management | `aicrm_next.commerce` | D2 retired old readonly owner | admin product owner removed | product writes and payment checkout blocked | D6.5 scan completed | D7 product/payment replacement planning |
| Customer Read Model | `aicrm_next.customer_read_model` | D3 retired old readonly owner | customer dependency fallback retained | archive, contacts, identity blocked | D6.5 scan completed | D7 customer external replacement planning |
| User Ops | `aicrm_next.ops_enrollment` | D4 retired old readonly owner | domain write/job fallback retained | DND, batch-send, deferred jobs, WeCom dispatch blocked | D6.5 scan completed | D7 User Ops replacement planning |
| Questionnaire | `aicrm_next.questionnaire` | D5 retired old readonly owner | mixed submit/write/OAuth/external fallback retained | submit, OAuth, WeCom tag, external push blocked | D6.5 scan completed | D7 Questionnaire replacement planning |
| Automation | `aicrm_next.automation_engine` | D6 retired old readonly owner | mixed write/external/runtime fallback retained | manual override, activation webhook, OpenClaw, workflow, agent, WeCom blocked | D6.5 scan completed | D7 Automation replacement planning |
| D7 Planning | `aicrm_next.integration_gateway` plus module owners | readonly unaffected | all write/external/runtime fallback retained | all D7 blocker matrix rows blocked | planning_ready | start D7.1 Media storage / WeCom media adapter contract |

Production traffic has not been cut by D6.5. Real external adapters remain disabled for this cleanup.
