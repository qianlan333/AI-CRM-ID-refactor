# Remaining Work Queue

## Current State

- D6.5 Dead Legacy Cleanup: completed for no-reference readonly leftovers.
- Actual D6.5 deletion: old attachment-library template and stale generated route inventory artifacts.
- D7 Write / External capability replacement planning: planning_ready.
- Production traffic cutover: not executed.
- Real external adapters: not executed by this cleanup.

## Next Work

| priority | work_item | status | notes |
| --- | --- | --- | --- |
| P0 | D6.5 acceptance audit | ready_for_review | run `tools/check_legacy_dead_cleanup.py`, fallback smoke, pytest, and six parity checks |
| P0 | D7 Write / External capability replacement planning | planning_ready | use `docs/d7_write_external_replacement_plan.md` and start with D7.1 |
| P0 | D7.1 Media storage / WeCom media adapter contract | next | define fake/staging/production adapter boundaries before any implementation |
| P1 | Media upload replacement plan | blocked | cloud storage and WeCom media require adapter evidence |
| P1 | Payment replacement plan | blocked | WeChat Pay and Alipay need provider sandbox and production callback evidence |
| P1 | Questionnaire submit/OAuth/external push replacement plan | blocked | needs real OAuth and external delivery approval |
| P1 | Automation runtime/OpenClaw replacement plan | blocked | needs workflow, agent, OpenClaw, and WeCom dispatch safety |

Codex should not execute production canary, set production route flags, call external services, or mark any module as approved for production.
