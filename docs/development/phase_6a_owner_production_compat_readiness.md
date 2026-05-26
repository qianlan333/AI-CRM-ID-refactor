# Phase 6A Owner Production Compat Readiness

## Status

- phase_6a_owner_production_compat_readiness
- no runtime change
- no production owner switch
- no fallback removal
- no production_compat behavior change
- no timer / automation execution
- no outbound send
- no destructive migration
- delete_ready false

## Phase 5 Handoff Summary

Phase 5 completed as external adapter live-capability tooling under explicit gates. The aggregate acceptance in PR #756 did not authorize live external calls by default, wider rollout, owner switch, fallback removal, production_compat narrowing, destructive cleanup, or delete readiness.

The handoff into Phase 6 is:

- production owner switch deferred to Phase 6
- fallback removal deferred to Phase 7
- production_compat narrowing deferred to Phase 6 or Phase 7
- delete_ready remains false

## Phase 6 Scope Definition

Phase 6 may plan and later implement, only through separately approved bundles:

- production route owner switch readiness
- production owner switch canary
- production_compat narrowing readiness
- fallback shadow comparison
- rollback path validation
- controlled timer / automation execution readiness
- controlled external adapter enablement review
- route ownership manifest update

This Phase 6A PR does not allow:

- owner switch execution
- production_compat behavior narrowing
- fallback removal
- timer execution
- outbound send
- delete_ready

## Candidate Inventory

| route_family | capability_owner | current_phase_completion | production owner switch ready | production_compat narrowing ready | fallback removal ready | required evidence | blockers | risk level | rollback requirement | recommended next Phase 6 bundle |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/admin/automation-conversion/profile-segment-templates*` | `aicrm_next.automation_engine` | Phase 4 accepted; production readonly dry-run evidence and review complete | true for canary planning only | false | false | manifest route diff, shadow read/write comparison, production readonly evidence replay, owner approval, rollback smoke | owner/config approval still required; fallback retained | low-medium | restore production_compat legacy_forward and retained fallback immediately | phase_6b_first_owner_switch_canary_plan_bundle |
| `/api/admin/automation-conversion/action-templates*` | `aicrm_next.automation_engine` | Phase 4 accepted as awaiting approval/config | false | false | false | staging owner approval, rollback owner, production dry-run gates | missing staging owner approval/config | medium | keep legacy fallback and defer route owner change | defer_to_later_phase6_owner_approval_bundle |
| `/api/admin/automation-conversion/task-groups*` | `aicrm_next.automation_engine` | Phase 4 accepted; fixture/native, repository adapter parity, staging readiness, and production readonly dry-run readiness complete as blocked evidence | true for canary planning only | false | false | production readonly evidence replay, exact-route manifest canary plan, fallback shadow comparison, rollback smoke, owner approval | production dry-run approval, config review, route-specific DB URL | low | restore legacy_forward route owner and fallback; revert canary config only | phase_6b_first_owner_switch_canary_plan_bundle |
| `/api/admin/automation-conversion/tasks*` | `aicrm_next.automation_engine` | Phase 4 accepted; production readonly dry-run readiness complete as blocked evidence | false | false | false | execution-disabled contract proof, production readonly evidence replay, rollback smoke | task execution remains deferred; config gates missing | medium | retain legacy fallback and disable task execution gates | defer_to_later_phase6_execution_readiness_bundle |
| `/api/admin/automation-conversion/workflows*` | `aicrm_next.automation_engine` | Phase 4 accepted; production readonly dry-run readiness complete as blocked evidence | false | false | false | workflow execution-disabled proof, production readonly evidence replay, rollback smoke | workflow execution deferred; config gates missing | medium | retain legacy fallback and disable workflow execution gates | defer_to_later_phase6_execution_readiness_bundle |
| `/api/admin/automation-conversion/workflow-nodes*` | `aicrm_next.automation_engine` | Phase 4 accepted; fixture/native, repository adapter parity, staging readiness, and production readonly dry-run readiness complete as blocked evidence | true for canary planning only | false | false | production readonly evidence replay, exact-route manifest canary plan, fallback shadow comparison, rollback smoke, owner approval | production dry-run approval, config review, route-specific DB URL | low | restore legacy_forward route owner and fallback; revert canary config only | phase_6b_first_owner_switch_canary_plan_bundle_alternate |
| `/api/admin/automation-conversion/agents*` | `aicrm_next.automation_engine` | Phase 4 accepted as staging readiness; production readonly dry-run bundle not claimed | false | false | false | production readonly dry-run readiness, execution-disabled proof, LLM adapter disabled proof | production readonly dry-run not complete; agent execution and LLM adapters deferred | high | keep legacy fallback and all execution adapters disabled | defer_to_later_phase6_agent_readiness_bundle |
| `/api/admin/automation-conversion/agent-runs*` | `aicrm_next.automation_engine` | Phase 4 accepted; production readonly dry-run readiness complete as blocked evidence | false | false | false | replay/orchestration disabled proof, readonly evidence replay, rollback smoke | replay/orchestration deferred; config gates missing | high | retain fallback and keep orchestration execution disabled | defer_to_later_phase6_agent_run_readiness_bundle |
| `/api/admin/automation-conversion/agent-outputs*` | `aicrm_next.automation_engine` | Phase 4 accepted; production readonly dry-run readiness complete as blocked evidence | false | false | false | export/download disabled proof, readonly evidence replay, rollback smoke | output export/download deferred; config gates missing | medium | retain fallback and keep export/download disabled | defer_to_later_phase6_agent_output_readiness_bundle |
| `/api/admin/wecom/tags*` | `aicrm_next.customer_tags` | Phase 5 family acceptance complete under explicit gates | false | false | false | live adapter gates, staging canary evidence, production target safety, cleanup proof, owner approval | external write risk; no wider rollout; no owner switch | high | disable live flags, cleanup tag changes, restore legacy fallback | defer_to_phase6_external_adapter_review |
| `/wecom/external-contact/callback` | `aicrm_next.integration_gateway` | Phase 5 family acceptance complete under explicit gates | false | false | false | callback ownership canary, idempotency evidence, rollback callback routing, owner approval | callback ownership cutover is high risk | high | restore callback owner and legacy processing immediately | defer_to_phase7_or_later_callback_cutover |
| `/api/h5/wechat/oauth*` | `aicrm_next.questionnaire` | Phase 5 family acceptance complete under explicit gates | false | false | false | identity/session parity, callback rollback, token persistence proof, owner approval | OAuth callback ownership and identity persistence risk | high | restore callback route and session fallback | defer_to_phase7_or_later_oauth_cutover |
| `/api/admin/image-library*` | `aicrm_next.media_library` | Phase 5 family acceptance complete under explicit gates | false | false | false | provider upload dry-run, file mutation rollback, storage cleanup, owner approval | live upload/storage mutation risk | high | disable upload provider and retain fallback | defer_to_phase6_external_adapter_review |
| `/api/admin/wechat-pay*` | `aicrm_next.commerce` | Phase 5 family acceptance complete under explicit gates | false | false | false | sandbox-only proof, no-money-movement proof, reconciliation rollback, owner approval | payment money movement must not be first Phase 6B candidate | critical | disable payment live flags and retain legacy commerce fallback | defer_to_phase7_payment_cutover |
| `/mcp` | `aicrm_next.integration_gateway` / `aicrm_next.ai_assist` | Phase 5 family acceptance complete under explicit gates | false | false | false | single prompt/tool canary gates, no outbound send proof, no automation proof, owner approval | external AI/tool call and outbound-send risk | high | disable MCP/OpenClaw live flags and retain fallback | defer_to_phase6_external_adapter_review |
| `/api/h5/questionnaires*` | `aicrm_next.questionnaire` | Phase 5 family acceptance complete under explicit gates | false | false | false | public submit canary, tag writeback disabled proof, rollback submit path, owner approval | external submit/writeback edge risk | high | restore legacy submit route and disable tag writeback | defer_to_phase7_submit_cutover |

## First Phase 6 Candidate Selection

Selected first Phase 6B candidate: `/api/admin/automation-conversion/task-groups*`.

Why selected:

- it is an internal metadata route family, not an external adapter
- it has Phase 4 fixture/native, repository adapter parity, staging readiness, and production readonly dry-run readiness evidence
- it does not require timer execution, automation execution, outbound send, payment movement, callback ownership cutover, or fallback removal
- rollback is clear: restore the retained production_compat legacy_forward owner and fallback, then revert only the canary/config package

This selection does not authorize owner switch execution. It only recommends the next planning bundle.

Payment, OAuth, and WeCom callback are not selected as the first Phase 6B candidate because they require external side-effect or callback-ownership risk that should remain deferred.

## Phase 6B Recommendation

- next bundle: phase_6b_first_owner_switch_canary_plan_bundle
- route_family: `/api/admin/automation-conversion/task-groups*`
- Phase 6A does not implement Phase 6B
- owner switch execution allowed: false
- production_compat change allowed: false
- fallback removal allowed: false

## Production Behavior

Production behavior is unchanged. No route owner changes, production_compat behavior changes, fallback changes, timer execution, automation execution, outbound send, live external calls, destructive migrations, or delete readiness are introduced.

## Fallback Behavior

Legacy fallback is retained for every candidate. Phase 6A records which fallback paths must remain in place and which evidence would be required before any later narrowing plan.

## Business Continuity

Daily production usage remains on the current behavior. Phase 6A only creates the rules for later canary planning and keeps rollback requirements explicit before any production switch work.

## Business Value

The bundle turns the Phase 4 internal-write and Phase 5 external-adapter acceptance evidence into a ranked Phase 6 owner-switch decision framework. That gives the next PR a small, low-risk first candidate instead of treating all production_compat routes as equally ready.

## Architecture Boundary

Phase 6A is docs, YAML, checker, tests, and phase-state policy only. Runtime directories, deployment config, migrations, production_compat runtime files, legacy Flask entry points, timers, automation execution, and outbound integrations are outside this PR.

## Safety / Non-goals

- no production owner switch
- no production_compat behavior change
- no fallback removal
- no timer execution
- no automation execution
- no outbound send
- no external adapter enablement
- no payment movement
- no callback ownership cutover
- no destructive migration
- no delete_ready

## Verification

Required verification:

- `python3 tools/check_phase6a_owner_production_compat_readiness.py --output-md /tmp/phase6a_owner_production_compat_readiness.md --output-json /tmp/phase6a_owner_production_compat_readiness.json`
- `python3 -m pytest tests/test_phase6a_owner_production_compat_readiness.py -q`
- `python3 -m py_compile tools/check_phase6a_owner_production_compat_readiness.py tools/check_autonomous_development_loop.py tools/check_automerge_eligibility.py tools/run_codex_autopilot_tick.py tests/test_phase6a_owner_production_compat_readiness.py`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py -q`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / Rollback

Risk is low because this PR has no runtime behavior change. Rollback is to revert this PR; production behavior, fallback, and production_compat remain as they were before Phase 6A.

## Autopilot Decision

Autopilot may record Phase 6A readiness as a policy bundle only. It must not advance into Phase 6B execution, owner switch, production_compat narrowing, fallback removal, timers, automation execution, outbound send, or destructive cleanup from this PR.

## Next Bundle Recommendation

If this PR merges:

- next: phase_6b_first_owner_switch_canary_plan_bundle
- route_family: `/api/admin/automation-conversion/task-groups*`

This PR must not implement Phase 6B.

## Baseline Blockers

- Existing legacy facade growth freeze baseline blockers may still be reported by the baseline checker.
- Local architecture skill compliance may be blocked by a missing local `yaml` dependency; if so, record it as an environment blocker rather than a pass.

## PR Lifecycle

This task is complete only when the PR reaches one of:

- merged into main, with PR number, merge commit, and main containment recorded
- blocked, with the exact blocker recorded
- closed without merge, with reason and next step recorded
