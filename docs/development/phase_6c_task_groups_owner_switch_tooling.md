# Phase 6C Task Groups Owner Switch Tooling

## Status

- phase_6c_task_groups_owner_switch_tooling
- bundle type: phase_6c_task_groups_owner_switch_tooling_bundle
- route family: `/api/admin/automation-conversion/task-groups*`
- tooling and evidence only
- no runtime route owner switch
- no production_compat behavior change
- fallback retained
- no timer / automation execution
- no outbound send
- no destructive migration
- delete_ready false

## Tooling Decision

Phase 6C adds default-blocked owner switch canary, shadow compare, and rollback evidence runners. It does not modify runtime routers or production_compat because a safe default-off runtime gate is not required for this readiness step. The current production route owner remains unchanged unless a later owner-approved bundle changes it.

## Required Gates

Owner switch canary evidence requires all env gates:

- `AICRM_PHASE6C_TASK_GROUPS_OWNER_SWITCH_APPROVED=1`
- `AICRM_PHASE6C_TASK_GROUPS_CONFIG_REVIEWED=1`
- `AICRM_PHASE6C_TASK_GROUPS_ROLLBACK_OWNER_APPROVED=1`
- `AICRM_PHASE6C_TASK_GROUPS_SHADOW_COMPARE_PASSED=1`

and all confirmations:

- `--confirm-owner-switch-canary`
- `--confirm-fallback-retained`
- `--confirm-production-compat-unchanged`
- `--confirm-rollback-ready`

Without all gates, the canary runner produces blocked evidence and exits successfully without owner switch execution.

## Runners

- `tools/run_phase6c_task_groups_owner_switch_canary.py`
- `tools/run_phase6c_task_groups_shadow_compare.py`
- `tools/run_phase6c_task_groups_owner_switch_rollback.py`

Default runner evidence records:

- owner_switch_executed: false
- production_compat_changed: false
- fallback_removed: false
- timer_execution_triggered: false
- automation_execution_triggered: false
- outbound_send_triggered: false

## Production Behavior

Production behavior is unchanged. The current production path and fallback remain in place.

## Fallback Behavior

Fallback is retained. Rollback evidence assumes the current fallback remains available.

## Business Continuity

Daily production use remains untouched. Phase 6C makes the next canary review safer by requiring explicit approvals, shadow evidence, and rollback evidence before any later route-owner change can be considered.

## Business Value

Task-groups gets a repeatable, auditable owner switch evidence workflow before any production behavior changes. This becomes the pattern for other low-risk internal metadata routes.

## Architecture Boundary

This bundle is docs, YAML, checker, tests, phase state, autopilot policy, and standalone evidence runners only. It does not change runtime routing, production_compat, fallback behavior, legacy Flask, deploy config, migrations, timers, automation execution, or outbound integrations.

## Safety / Non-goals

- no default-on owner switch
- no runtime owner switch
- no fallback removal
- no production_compat behavior change
- no timer execution
- no automation execution
- no outbound send
- no destructive migration
- no delete_ready

## Verification

- `python3 tools/check_phase6c_task_groups_owner_switch_tooling.py --output-md /tmp/phase6c_task_groups_owner_switch_tooling.md --output-json /tmp/phase6c_task_groups_owner_switch_tooling.json`
- `python3 -m pytest tests/test_phase6c_task_groups_owner_switch_tooling.py -q`
- `python3 tools/run_phase6c_task_groups_owner_switch_canary.py --output-json /tmp/phase6c_task_groups_canary_default.json`
- `python3 tools/run_phase6c_task_groups_shadow_compare.py --output-json /tmp/phase6c_task_groups_shadow_default.json`
- `python3 tools/run_phase6c_task_groups_owner_switch_rollback.py --output-json /tmp/phase6c_task_groups_rollback_default.json`
- `python3 -m py_compile tools/check_phase6c_task_groups_owner_switch_tooling.py tools/run_phase6c_task_groups_owner_switch_canary.py tools/run_phase6c_task_groups_shadow_compare.py tools/run_phase6c_task_groups_owner_switch_rollback.py tools/check_autonomous_development_loop.py tools/check_automerge_eligibility.py tools/run_codex_autopilot_tick.py tests/test_phase6c_task_groups_owner_switch_tooling.py`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py -q`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / Rollback

Risk is low because this PR adds default-blocked evidence runners only. Rollback is reverting this PR.

## Autopilot Decision

Autopilot may record Phase 6C tooling as complete. It must not run owner switch execution, production_compat changes, fallback removal, timer execution, automation execution, outbound send, or destructive migration from this PR.

## Next Bundle Recommendation

- next: phase_6d_internal_metadata_owner_switch_batch_bundle
- route families: `/api/admin/automation-conversion/task-groups*`, `/api/admin/automation-conversion/workflow-nodes*`, `/api/admin/automation-conversion/agent-outputs*`

## Baseline Blockers

- Existing legacy facade growth freeze baseline direct legacy imports may still be reported.
- Local architecture skill compliance may be blocked by missing local `yaml` dependency; record that as environment blocker, not a pass.

## PR Lifecycle

This PR is complete only after it is merged into main and main contains the merge commit, or after an exact blocker/close reason is recorded.
