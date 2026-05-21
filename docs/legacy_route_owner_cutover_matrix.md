# Legacy Route Owner Cutover Matrix

| Batch | Module | Next Owner | Legacy Owner | Current Status | Delete Gate |
| --- | --- | --- | --- | --- | --- |
| D0 | Freeze only | `ai_crm_next` default runtime | `legacy_flask` fallback | frozen | no deletion |
| D1 | Media readonly | `aicrm_next.media_library` | legacy media routes | retired/deleted | completed by D1; rollback by reverting the D1 PR or restoring a pre-D1 legacy fallback tag |
| D2 | Product readonly | `aicrm_next.commerce` | legacy admin product route owner | retired/deleted | completed by D2; checkout/payment files are untouched and rollback is git revert/pre-D2 fallback tag |
| D3 | Customer readonly | `aicrm_next.customer_read_model` | legacy customer center/timeline route owner | retired/deleted | completed by D3; archive/contacts/identity fallback files are untouched and rollback is git revert/pre-D3 fallback tag |
| D4 | User Ops readonly | `aicrm_next.ops_enrollment` | legacy user ops admin route owner | retired/tombstoned | completed by D4; write/external User Ops domain helpers remain not delete-ready and rollback is git revert/pre-D4 fallback tag |
| D5 | Questionnaire readonly | `aicrm_next.questionnaire` | legacy questionnaire mixed readonly owner | retired/tombstoned | completed by D5; submit/OAuth/admin-write/external-push fallback files remain not delete-ready and rollback is git revert/pre-D5 fallback tag |
| D6 | Automation readonly | `aicrm_next.automation_engine` | legacy automation conversion | canary evidence available | production evidence and accepted route drift proof |
| D7 | Write/external adapters | Next adapters, if approved | legacy write/external routes | not approved | real external replacement evidence |
| D8 | Flask factory/http registrar | none | legacy app factory and HTTP registrar | not eligible | all routes retired |
| D9 | OpenClaw legacy adapter | Next-approved integration | legacy OpenClaw adapter | not eligible | external adapter replacement evidence |

No row is `production_ready` or `production_approved`.
