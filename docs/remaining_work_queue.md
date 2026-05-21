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
- D8 Legacy Flask shell retirement planning: retirement_planning_ready.
- D8.1 Legacy fallback route lockdown planning: lockdown_planning_ready.
- D8.2 Legacy fallback route lockdown enforcement: lockdown_enforcement_implemented.
- D8.3 Legacy Flask archive package move planning: archive_move_planning_ready.
- D8.4 Legacy Flask archive package implementation: archive_package_created.
- D8.5 Legacy DB / maintenance command retirement planning: maintenance_command_retirement_planning_ready.
- D9 OpenClaw legacy adapter physical retirement planning: openclaw_legacy_retirement_planning_ready.
- D9.1 OpenClaw legacy adapter import freeze: openclaw_import_freeze_ready.
- D9.2 OpenClaw legacy adapter move planning: openclaw_legacy_move_planning_ready.
- D9.3 OpenClaw legacy archive skeleton: openclaw_legacy_skeleton_created.
- D9.4 OpenClaw legacy files moved with shim: openclaw_legacy_files_moved_with_shim.
- D9.5 OpenClaw shim-removal planning: openclaw_shim_removal_planning_ready.
- D9.5.1 OpenClaw final reference scan: reference_scan_completed; pending_observation_evidence.
- D9.5.2 OpenClaw shim deletion blocked package: blocked_pending_observation_evidence.
- D9.6 OpenClaw shim physical deletion: openclaw_shim_physical_deletion_recorded.
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
| P0 | D8 Legacy Flask shell retirement planning | retirement_planning_ready | D8.0 adds plan, dependency inventory, allowed fallback matrix, checker, and tests only; no legacy shell deletion, production config change, or traffic cutover |
| P0 | D8.1 Legacy fallback route lockdown planning | lockdown_planning_ready | defines explicit allowed fallback route registry, retired readonly route matrix, checker, and tests without deleting shell core |
| P0 | D8.2 Legacy fallback route lockdown enforcement | lockdown_enforcement_implemented | legacy-only guard returns 410 for retired D1-D6 readonly routes while preserving documented allowed fallback routes |
| P0 | D8.3 Legacy Flask archive package planning | archive_move_planning_ready | planning only; `wecom_ability_service/` and `openclaw_service/` remain in place and `legacy_flask/` is not created |
| P0 | D8.4 Legacy Flask archive package implementation | archive_package_created | entry layer moved to `legacy_flask/`; `wecom_ability_service/` remains compatibility shim and `openclaw_service/` remains retained |
| P0 | D8.5 Legacy DB / maintenance command retirement planning | maintenance_command_retirement_planning_ready | inventory, retirement plan, replacement matrix, checker, and tests exist; no command deletion or production DB migration execution |
| P0 | D9 OpenClaw legacy adapter physical retirement planning | openclaw_legacy_retirement_planning_ready | retirement plan, dependency inventory, compatibility matrix, checker, and tests exist; `openclaw_service/` remains retained and frozen |
| P0 | D9.1 Freeze OpenClaw legacy adapter imports | openclaw_import_freeze_ready | import freeze plan, allowlist, checker, and tests exist; new runtime imports of `openclaw_service` are blocked |
| P0 | D9.2 Move/archive OpenClaw legacy adapter | openclaw_legacy_move_planning_ready | move plan, move map, import rewrite plan, checker, and tests exist; D9.4 now records metadata-only archive with shim |
| P0 | D9.3 Create OpenClaw archive package skeleton | openclaw_legacy_skeleton_created | skeleton package exists; no move, no shim, no runtime owner |
| P0 | D9.4 Move OpenClaw files with compatibility shim | openclaw_legacy_files_moved_with_shim | metadata-only marker archived; shim retained; no runtime owner |
| P0 | D9.5 OpenClaw shim-removal planning | openclaw_shim_removal_planning_ready | plan, final reference scan plan, readiness checklist, checker, and tests exist; shim retained |
| P0 | D9.5.1 OpenClaw final reference scan and observation evidence | reference_scan_completed_pending_observation | repository scan captured zero Next runtime imports and zero deploy/script hits; runtime observation logs, workload evidence, rollback independence, and signoff remain pending |
| P0 | D9.5.2 OpenClaw shim deletion blocked package | blocked_pending_observation_evidence | deletion candidate is false; shim retained; only production/runtime observation evidence, workload proof, rollback independence, and signoff remain before any deletion PR |
| P0 | D9.6 OpenClaw shim physical deletion | openclaw_shim_physical_deletion_recorded | owner approved deleting repo shim/archive and server OpenClaw-named jobs; server backup recorded at `/home/ubuntu/backups/openclaw-retirement-20260522004443` |
| P0 | D8.6 Legacy app factory / HTTP registrar removal planning | blocked | future planning only; no removal before production evidence, command replacement, and rollback signoff |
| P1 | Media upload replacement plan | blocked | cloud storage and WeCom media require staging/provider evidence before real calls |
| P1 | User Ops real dispatch/deferred-job implementation | blocked | D7.3 fake contract exists; needs staging allowlist, queue lease, operator approval, and rollback evidence |
| P1 | Payment replacement plan | blocked | D7.4 fake contract exists; WeChat Pay and Alipay still need provider sandbox, signing, reconciliation, and production callback evidence |
| P1 | Questionnaire submit/OAuth/external push real-call implementation | blocked | D7.2 fake contract exists; needs real OAuth, WeCom tag, webhook staging evidence and approval |
| P1 | Automation runtime/OpenClaw real-call implementation | blocked | D7.5 fake contracts exist; needs workflow idempotency, agent output dedupe, OpenClaw retry/dead-letter, credentials policy, and explicit approval |
| P1 | Customer sync real-call implementation | blocked | D7.6 fake contracts exist; needs archive cursor locking, contacts merge policy, identity no-leak guard, projection replay safety, credentials policy, and explicit approval |
| P1 | MCP/OpenClaw real-call implementation | blocked | D7.7 fake contracts exist; needs MCP allowlist, bearer-token policy, OpenClaw retry/replay guard, compatibility evidence, and explicit approval |

Codex should not execute production canary, set production route flags, call external services, or mark any module as approved for production.
