# Phase 6B Task Groups Owner Switch Canary Plan

## Status

- phase_6b_task_groups_owner_switch_canary_plan
- bundle type: phase_6b_first_owner_switch_canary_plan_bundle
- route family: `/api/admin/automation-conversion/task-groups*`
- no runtime change
- no production owner switch execution
- no production_compat behavior change
- fallback retained
- no timer / automation execution
- no outbound send
- no destructive migration
- delete_ready false

## Current Owner Status

The task-groups route family is currently retained behind the existing production path and fallback boundary. Phase 4 accepted the route family for internal metadata readiness with fixture/native, repository adapter parity, staging readiness, and production readonly dry-run readiness as blocked evidence. Phase 6A selected this route family as the first low-risk internal metadata candidate for owner switch canary planning.

Current production behavior remains unchanged in Phase 6B:

- current owner: `production_compat_legacy_forward_with_retained_fallback`
- proposed Next owner: `aicrm_next.automation_engine`
- production_compat unchanged
- fallback retained
- owner switch execution not authorized

## Canary Plan

The first canary must be exact-route and owner-approved. It must not use a broad wildcard production_compat change.

Required canary preconditions:

- owner approval for `/api/admin/automation-conversion/task-groups*`
- production config review
- rollback owner approval
- shadow compare evidence
- rollback rehearsal evidence
- confirmation that fallback remains retained
- confirmation that production_compat behavior is unchanged

The canary plan is a later Phase 6C/6D tooling concern. Phase 6B only defines the plan and evidence requirements.

## Production Shadow Compare Plan

Shadow compare must compare the proposed Next owner output against the retained current production path without switching default production traffic.

Required evidence:

- route-family request inventory
- read/list response shape comparison
- create/update validation comparison if represented as dry-run only
- error/degraded response comparison
- no fixture/local_contract production success
- no timer, execution, or outbound send side effects

Shadow compare must be blocked by default until explicit approval and required flags are present in a later tooling bundle.

## Rollback Plan

Rollback requirement:

- keep fallback retained
- keep production_compat unchanged
- restore the current route owner by disabling the canary flag
- preserve legacy forward behavior for the exact route family
- record rollback evidence before any later canary execution

Rollback cannot require a destructive migration, fallback deletion, production_compat behavior change, timer execution, automation execution, or outbound send.

## Owner Approval Checklist

- route family confirmed: `/api/admin/automation-conversion/task-groups*`
- capability owner confirmed: `aicrm_next.automation_engine`
- production owner switch scope is exact-route only
- fallback retained
- production_compat unchanged
- rollback owner assigned
- shadow compare evidence reviewed
- no timer / automation execution
- no outbound send
- no destructive migration
- delete_ready remains false

## Production Route Ownership Manifest Proposed Delta

Proposed future delta only, not implemented in Phase 6B:

- route pattern: `/api/admin/automation-conversion/task-groups*`
- proposed current_runtime_owner during canary: `next_canary_behind_explicit_flag`
- capability owner: `aicrm_next.automation_engine`
- production behavior: `owner_switch_canary_shadow_compared`
- legacy fallback allowed: true
- delete_ready: false

This PR does not edit the route ownership manifest because Phase 6B is a planning bundle. A later execution/tooling bundle must include manifest evidence if it changes any owner field.

## Production Behavior

Production behavior remains unchanged. No default owner switch is performed.

## Fallback Behavior

Fallback is retained and must remain available through the later canary and rollback flow.

## Business Continuity

Daily production usage remains on the existing production path. Phase 6B reduces risk by requiring shadow compare and rollback evidence before any owner switch canary can run.

## Business Value

Task-groups is a low-risk internal metadata route family. Planning it first creates a reusable, exact-route owner switch canary pattern before higher-risk routes are considered.

## Architecture Boundary

This bundle is docs, YAML, checker, tests, phase state, and autopilot policy only. It does not modify runtime routers, production_compat, legacy Flask, deployment config, migrations, timers, or external adapters.

## Safety / Non-goals

- no runtime owner switch
- no production_compat behavior change
- no fallback removal
- no default-on canary
- no timer execution
- no automation execution
- no outbound send
- no destructive migration
- no delete_ready

## Verification

- `python3 tools/check_phase6b_task_groups_owner_switch_canary_plan.py --output-md /tmp/phase6b_task_groups_owner_switch_canary_plan.md --output-json /tmp/phase6b_task_groups_owner_switch_canary_plan.json`
- `python3 -m pytest tests/test_phase6b_task_groups_owner_switch_canary_plan.py -q`
- `python3 -m py_compile tools/check_phase6b_task_groups_owner_switch_canary_plan.py tools/check_autonomous_development_loop.py tools/check_automerge_eligibility.py tools/run_codex_autopilot_tick.py tests/test_phase6b_task_groups_owner_switch_canary_plan.py`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py -q`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / Rollback

Risk is low because Phase 6B has no runtime change. Rollback is reverting this PR.

## Autopilot Decision

Autopilot may record this bundle as completed planning only. It must not run owner switch execution, production_compat changes, fallback removal, timer execution, automation execution, outbound send, or destructive migration from this PR.

## Next Bundle Recommendation

- next: phase_6c_task_groups_owner_switch_tooling_bundle
- route_family: `/api/admin/automation-conversion/task-groups*`

## Baseline Blockers

- Existing legacy facade growth freeze baseline direct legacy imports may still be reported.
- Local architecture skill compliance may be blocked by missing local `yaml` dependency; record that as environment blocker, not a pass.

## PR Lifecycle

This PR is complete only after it is merged into main and main contains the merge commit, or after an exact blocker/close reason is recorded.
