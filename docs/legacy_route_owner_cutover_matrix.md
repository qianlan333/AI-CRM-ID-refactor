# Legacy Route Owner Cutover Matrix

| Batch | Module | Next Owner | Legacy Owner | Current Status | Delete Gate |
| --- | --- | --- | --- | --- | --- |
| D0 | Freeze only | `ai_crm_next` default runtime | `legacy_flask` fallback | frozen | no deletion |
| D1 | Media readonly | `aicrm_next.media_library` | legacy media routes | retired/deleted | completed by D1; rollback by reverting the D1 PR or restoring a pre-D1 legacy fallback tag |
| D2 | Product readonly | `aicrm_next.commerce` | legacy admin product route owner | retired/deleted | completed by D2; checkout/payment files are untouched and rollback is git revert/pre-D2 fallback tag |
| D3 | Customer readonly | `aicrm_next.customer_read_model` | legacy customer center/timeline route owner | retired/deleted | completed by D3; archive/contacts/identity fallback files are untouched and rollback is git revert/pre-D3 fallback tag |
| D4 | User Ops readonly | `aicrm_next.ops_enrollment` | legacy user ops admin route owner | retired/tombstoned | completed by D4; write/external User Ops domain helpers remain not delete-ready and rollback is git revert/pre-D4 fallback tag |
| D5 | Questionnaire readonly | `aicrm_next.questionnaire` | legacy questionnaire mixed readonly owner | retired/tombstoned | completed by D5; submit/OAuth/admin-write/external-push fallback files remain not delete-ready and rollback is git revert/pre-D5 fallback tag |
| D6 | Automation readonly | `aicrm_next.automation_engine` | legacy automation conversion mixed readonly owner | retired/tombstoned | completed by D6; manual override, activation webhook, OpenClaw, workflow/runtime, agent, and WeCom fallback files remain not delete-ready |
| D6.5 | Dead legacy cleanup | no route owner change | D1-D6 stale readonly leftovers | completed | deleted only unreferenced attachment template and stale generated route inventory; D7 blockers remain protected |
| D7 | Write/external adapters | Next fake/staging-disabled adapter contracts | legacy write/external routes | accepted through D7.7 | no deletion until real replacement evidence, rollback proof, and signoff |
| D8 | Flask factory/http registrar and maintenance commands | `aicrm_next.main` default runtime remains active | `legacy_flask/` entry layer plus `wecom_ability_service/` compatibility shim and retained maintenance commands | maintenance_command_retirement_planning_ready | D8.5 plans maintenance command replacement; no shell deletion, command deletion, DB migration execution, or production cutover |
| D9 | OpenClaw legacy adapter | `aicrm_next.integration_gateway` D7.7 fake/staging-disabled contracts | `openclaw_service/` frozen legacy reference | openclaw_import_freeze_ready | no physical removal until import freeze acceptance, real replacement evidence, docs/scripts rewrite, plugin compatibility validation, rollback proof, and human signoff |

No row is approved for production.
