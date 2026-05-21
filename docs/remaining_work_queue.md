# Remaining Work Queue

## Current State

- D6.5 Dead Legacy Cleanup: completed for no-reference readonly leftovers.
- Actual D6.5 deletion: old attachment-library template and stale generated route inventory artifacts.
- D7 Write / External capability replacement planning: planning_ready.
- D7.1 Media storage / WeCom media adapter contract: accepted_prerequisite.
- D7.2 Questionnaire submit / OAuth / WeCom tag / external push adapter contract: accepted_prerequisite.
- D7.3 User Ops DND / batch-send / WeCom dispatch / deferred jobs adapter contract: accepted_prerequisite.
- D7.4 Product writes / WeChat Pay / Alipay / notify / return adapter contract: scope_isolated.
- D7.5 Automation write / OpenClaw / workflow runtime / agent runtime adapter contract: fake_contract_ready.
- D7.6 Archive sync / Contacts sync / Identity mapping / Customer projection adapter contract: fake_contract_ready.
- D7.7 MCP / OpenClaw legacy adapter contract: fake_contract_ready.
- Production traffic cutover: not executed.
- Real external adapters: not executed by this cleanup.

## Next Work

| priority | work_item | status | notes |
| --- | --- | --- | --- |
| P0 | D6.5 acceptance audit | ready_for_review | run `tools/check_legacy_dead_cleanup.py`, fallback smoke, pytest, and six parity checks |
| P0 | D7 Write / External capability replacement planning | planning_ready | use `docs/d7_write_external_replacement_plan.md` and start with D7.1 |
| P0 | D7.1 Media storage / WeCom media adapter contract | accepted_prerequisite | keep as baseline for D7.4 scope isolation; real cloud and WeCom upload remain blocked |
| P0 | D7.2 Questionnaire submit/OAuth/WeCom tag/external push adapter contract | accepted_prerequisite | keep as baseline for D7.4 scope isolation; real OAuth, WeCom tag writes, and webhook delivery remain blocked |
| P0 | D7.3 User Ops DND/batch-send/WeCom dispatch/deferred jobs adapter contract | accepted_prerequisite | keep as baseline for D7.4 scope isolation; real DND writes, WeCom dispatch, and deferred job execution remain blocked |
| P0 | D7.4 Product writes/WeChat Pay/Alipay/notify/return adapter contract | scope_isolated | D7.4 scope isolation accepted; real product writes, payment provider calls, and production notify processing remain blocked |
| P0 | D7.5 Automation adapter contract | fake_contract_ready | run D7.5 checker, tests, Automation smoke, and Automation parity for acceptance; real Automation writes, activation side effects, OpenClaw, workflow runtime, and agent runtime remain blocked |
| P0 | D7.6 Archive/Contacts/Identity adapter contract | fake_contract_ready | run D7.6 checker, tests, Customer smoke, and Customer parity for acceptance; real WeCom archive, contacts sync, identity writes, and customer projection writes remain blocked |
| P0 | D7.7 MCP/OpenClaw legacy adapter contract | fake_contract_ready | run D7.7 checker, tests, Customer smoke/parity, and Automation smoke/parity for acceptance; real MCP external calls, OpenClaw calls, webhooks, and physical OpenClaw legacy deletion remain blocked |
| P1 | Media upload replacement plan | blocked | cloud storage and WeCom media require staging/provider evidence before real calls |
| P1 | User Ops real dispatch/deferred-job implementation | blocked | D7.3 fake contract exists; needs staging allowlist, queue lease, operator approval, and rollback evidence |
| P1 | Payment replacement plan | blocked | D7.4 fake contract exists; WeChat Pay and Alipay still need provider sandbox, signing, reconciliation, and production callback evidence |
| P1 | Questionnaire submit/OAuth/external push real-call implementation | blocked | D7.2 fake contract exists; needs real OAuth, WeCom tag, webhook staging evidence and approval |
| P1 | Automation runtime/OpenClaw real-call implementation | blocked | D7.5 fake contracts exist; needs workflow idempotency, agent output dedupe, OpenClaw retry/dead-letter, credentials policy, and explicit approval |
| P1 | Customer sync real-call implementation | blocked | D7.6 fake contracts exist; needs archive cursor locking, contacts merge policy, identity no-leak guard, projection replay safety, credentials policy, and explicit approval |
| P1 | MCP/OpenClaw real-call implementation | blocked | D7.7 fake contracts exist; needs MCP allowlist, bearer-token policy, OpenClaw retry/replay guard, compatibility evidence, and explicit approval |

Codex should not execute production canary, set production route flags, call external services, or mark any module as approved for production.
