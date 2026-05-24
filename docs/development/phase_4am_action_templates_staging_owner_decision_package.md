# Phase 4AM Action Templates Staging Owner Decision Package

## Summary

Phase 4AM action-templates staging approval/config closure is still incomplete after PR #643. Autopilot cannot safely execute staging smoke or proceed toward production dry-run until owners provide the missing approvals and configuration facts.

This owner decision package is intentionally manual-only:

- It must be labeled `owner-decision-required`.
- It must be labeled `automerge-blocked`.
- It must not be labeled as safe for autopilot merge.
- It must never auto-merge.

## Architecture Boundary

Capability owner:

- `aicrm_next.automation_engine`

Staging approval/config decision boundary:

- `aicrm_next.integration_gateway`

Route family:

- `/api/admin/automation-conversion/action-templates*`

This package changes only documentation, YAML, checker/test coverage, and autonomous phase state. It does not add, remove, or modify any business route.

## Business Continuity

本 PR 只生成 Phase 4AM action-templates staging owner decision package，不连接 staging DB，不连接生产数据，不执行 staging smoke，不写生产，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。action-templates 当前 production path 仍由 legacy fallback 保持。

## Business Value

This package stops autopilot from looping on incomplete staging approval/config. It gives the user and owners one concrete decision checklist: approve/provide the staging configuration and owners, or keep action-templates paused and select a different low-risk Phase 4 work package.

## Current Blocker

The Phase 4AM closure package remains incomplete because all owner/config closure items are still pending:

- automation_engine owner approval.
- integration_gateway owner approval.
- staging DB/config owner approval.
- staging DB env confirmation.
- staging DB URL safety confirmation.
- smoke operator assignment.
- rollback owner assignment.
- evidence path agreement.
- write smoke approval decision.
- safe namespace cleanup strategy confirmation.
- side-effect safety confirmation.

## Why Autopilot Cannot Continue

Autopilot cannot execute staging smoke because the staging DB/config and owner approvals are not confirmed. Autopilot also cannot proceed to production dry-run because staging approval/config is incomplete.

Continuing automatically would risk converting missing human approval into implied staging readiness. That would violate the Phase 4 boundary.

## Required Owner Decisions

Owners must choose one safe path:

1. Provide all missing staging approval/config items so Phase 4AM can run owner-approved staging smoke evidence.
2. Keep action-templates paused and explicitly select a different low-risk Phase 4 candidate/package.
3. Ask for a narrower closure update if only some approval/config evidence is now available.

Required approvals/config if choosing staging smoke:

- automation_engine owner approval.
- integration_gateway owner approval.
- staging DB/config owner approval.
- `AICRM_ACTION_TEMPLATES_REPO_BACKEND=sqlalchemy`.
- `AICRM_ACTION_TEMPLATES_STAGING_DATABASE_URL` with a safe marker: `staging`, `stage`, `test`, `local`, or `dev`.
- Confirmation that the staging DB URL does not contain: `prod`, `production`, `primary`, or `master`.
- Smoke operator.
- Rollback owner.
- Read-only evidence path.
- Write smoke approval decision.
- Safe namespace cleanup strategy.

## Safe Next Options

Safe options:

- Owner-approved staging smoke evidence for action-templates, only after all approval/config items are complete.
- Keep action-templates waiting and move autopilot to another explicitly selected low-risk Phase 4 docs/checker/test package.
- Provide partial owner/config evidence and run another closure update package.

Unsafe options without explicit owner approval:

- staging smoke execution while approval/config remains incomplete.
- production dry-run.
- production write.
- production route ownership switch.
- fallback removal.
- `production_compat` change.
- real external calls.
- timer or automation execution.
- outbound send.

## Safety / Non-goals

This owner decision package does not authorize:

- staging smoke execution.
- production dry-run.
- production write.
- production repository route enablement.
- route ownership switch.
- fallback removal.
- `production_compat` change.
- real external calls.
- timer or automation execution.
- outbound send.
- canary approval.
- `delete_ready`.

## Verification

Run:

```bash
python3 tools/check_phase4am_action_templates_staging_owner_decision_package.py --output-md /tmp/phase4am_action_templates_staging_owner_decision_package.md --output-json /tmp/phase4am_action_templates_staging_owner_decision_package.json
python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json
python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json
python3 -m pytest tests/test_phase4am_action_templates_staging_owner_decision_package.py tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py -q
python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json
python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json
git diff --check
```

`tools/check_automerge_eligibility.py` is expected to report `eligible=false` with manual merge required because this is an owner decision package.

## Risk / Rollback

Risk is limited to owner decision wording. Rollback is reverting this PR. Runtime behavior, staging data, production data, route ownership, fallback behavior, `production_compat`, schema, and migrations are unchanged.

## Autopilot Decision

Autopilot selected an owner decision package because #643 closed the checklist structure, but the required owner/config items remain pending. This PR is manual-only and must not auto-merge.

## Next Action

The user or owners should provide the missing approval/config values, or explicitly redirect autopilot to a different low-risk Phase 4 package. Until then, action-templates remains awaiting staging approval/config and production dry-run must not start.
