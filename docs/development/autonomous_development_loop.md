# AI-CRM Codex Autopilot Development Loop

## Purpose

This protocol defines a bounded Codex autopilot loop for AI-CRM. The loop may inspect repository state every 15 minutes, choose the next low-risk action, open a PR, and mark that PR eligible for auto-merge only when the auto-merge eligibility gate passes and GitHub required checks pass.

The protocol does not authorize production owner switch, fallback removal, production write, real external calls, destructive migrations, deploy config changes, or canary approval.

## Business value

This gives future Codex runs a repeatable protocol for advancing low-risk Phase 4 work without waiting on manual orchestration for every docs/checker/test handoff. It keeps action-templates in staging-approval wait while allowing safe repository-state review, blocked evidence review, and owner decision packages to continue.

## Business continuity

This protocol does not change runtime behavior. It does not modify production routes, `production_compat`, deploy config, schema, migrations, or legacy fallback ownership. When a stop condition is detected, autonomous work stops and only an owner decision package may be produced.

## Risk / rollback

Risk is limited to protocol/checker misclassification. Rollback is to revert this PR and return to manual Phase 4 execution. Runtime production traffic remains on the existing owner paths.

## Next action

Future Codex loops may run the autonomous development checker and auto-merge eligibility checker before selecting a low-risk next action. Action-templates remains limited to Phase 4AM staging execution / approval config closure / blocked evidence review until owner approval/config is complete.

## Required Preflight

Every autopilot iteration must read and follow:

- `docs/development/codex_architecture_operating_memory.md`
- `docs/development/ai_crm_next_architecture_skill.md`
- `skills/ai-crm-next-architecture/SKILL.md`
- `docs/route_ownership/production_route_ownership_manifest.yaml`
- `docs/development/legacy_replacement_backlog.yaml`
- `docs/development/phase_execution_state.yaml`
- `docs/development/autonomous_stop_conditions.yaml`

## Loop Cadence

The loop may run every 15 minutes. Each run must:

1. Fetch latest `origin/main`.
2. Read `phase_execution_state.yaml`.
3. Confirm `active_candidate` exists in the route ownership manifest and legacy replacement backlog.
4. Select only one action from `next_allowed_actions`.
5. Stop if the selected action or current diff matches any stop condition.
6. Create a PR only for low-risk docs/checker/test/protocol work.
7. Run task-specific checkers and `tools/check_automerge_eligibility.py`.
8. Allow auto-merge only when GitHub required checks are green and the eligibility gate says `eligible: true`.

## Low-Risk Autopilot Actions

Low-risk actions are limited to:

- Docs/YAML planning or handoff updates.
- Checker/test additions for existing planning gates.
- Blocked evidence review packages.
- Owner decision package creation.
- Narrow allowlist maintenance in prior checker files.

## High-Risk Stop Behavior

When a high-risk stop condition appears, Codex must stop autonomous execution and generate only an owner decision package. It must not auto-merge.

High-risk stop examples:

- Production route owner switch.
- Fallback removal.
- Production write.
- Real external call.
- Timer or automation execution.
- Outbound send.
- Deploy config.
- Destructive migration.
- `delete_ready`.
- Canary approval.

## Current Action-Templates State

`/api/admin/automation-conversion/action-templates*` is waiting for staging approval/config. The current allowed next actions are limited to Phase 4AM staging execution / approval config closure / blocked evidence review. Production owner switch, production write, fallback removal, and production route enablement are not ready.

## Auto-Merge Rule

Auto-merge is allowed only when all are true:

- The diff is low-risk.
- The PR body includes Business value, Business continuity, Risk / rollback, and Next action.
- `tools/check_autonomous_development_loop.py` passes.
- `tools/check_automerge_eligibility.py` passes with `eligible: true`.
- GitHub required checks pass.
- No stop condition is touched.
- No unauthorized production readiness claim appears.

If any condition fails, auto-merge is forbidden and Codex must output a blocked status or owner decision package.
