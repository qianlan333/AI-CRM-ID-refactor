# Phase 4AM Action-Templates Owner Decision Package

## Summary

Action-templates is in staging approval/config wait. The autonomous loop has already recorded the blocked evidence in `docs/development/phase_execution_state.yaml`, and this package freezes the human decisions needed before any further staging evidence attempt.

## Architecture Boundary

Capability owner: `aicrm_next.automation_engine`.

Fallback boundary: `aicrm_next.integration_gateway`.

Route family: `/api/admin/automation-conversion/action-templates*`.

Current owner remains the legacy production compatibility fallback. This package is docs/state only and does not change runtime behavior.

## Business Continuity

Current daily automation configuration remains on the existing production path. This package does not connect to staging DB or production DB, does not write production data, does not change route ownership, does not remove fallback behavior, and does not enable external calls.

## Business Value

Autopilot should stop repeating blocked-evidence updates while staging access and approvals are missing. This package gives owners a small checklist for unblocking the next safe staging evidence run.

## Current Blockers

- Staging DB/config owner approval is missing.
- Staging DB environment is not confirmed.
- Staging DB URL safety is not confirmed.
- Smoke operator is not assigned.
- Rollback owner is not assigned.
- Evidence path is not agreed.
- Write smoke approval is not confirmed.
- Safe namespace cleanup strategy is not confirmed.

## Owner Decisions Needed

- Name the automation_engine owner approver.
- Name the integration_gateway owner approver.
- Confirm the staging DB/config owner.
- Assign a smoke operator.
- Assign a rollback owner.
- Confirm the evidence output path.
- Confirm whether write smoke is needed.
- Confirm safe namespace and cleanup rules.

## Safety / Non-Goals

- No staging smoke execution in this PR.
- No production data connection.
- No production write.
- No route ownership change.
- No fallback removal.
- No `production_compat` change.
- No deploy, nginx, or systemd change.
- No real external call, timer, automation execution, or outbound send.

## Verification

Required local checks for this package:

- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py -q`
- `python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / Rollback

Risk is limited to owner-decision documentation. Rollback is to revert this PR. Runtime and production traffic remain unchanged.

## Autopilot Decision

Autopilot detected `owner_approval_required: true` in `phase_execution_state.yaml` after PR #641 merged. This PR is an owner decision package and must not be auto-merged.

## Next Action

Owners should provide the missing staging approval/config decisions. After that, a later Phase 4AM PR may run staging evidence within the existing safety boundary.

## PR Lifecycle

- PR number: pending
- final PR state: pending
- merge commit if merged: pending
- whether main contains merge commit: pending
- blocker if not merged: owner decision required
