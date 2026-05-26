# Phase 6D Internal Metadata Owner Switch Batch

## Status

- phase_6d_internal_metadata_owner_switch_batch
- bundle type: phase_6d_internal_metadata_owner_switch_batch_bundle
- no runtime owner switch
- no production_compat behavior change
- fallback retained
- no timer / automation execution
- no outbound send
- no destructive migration
- delete_ready false

## Selected Route Families

The first internal metadata batch is limited to low-risk metadata routes:

- `/api/admin/automation-conversion/task-groups*`
- `/api/admin/automation-conversion/workflow-nodes*`
- `/api/admin/automation-conversion/agent-outputs*`

`tasks*` and `workflows*` remain optional later candidates because they can be confused with execution semantics. Payment, OAuth, WeCom external callback, media live provider, OpenClaw/MCP live call, timer/run-due, automation execution, and outbound send are excluded.

## Batch Tooling

This bundle adds a default-blocked batch evidence runner:

- `tools/run_phase6d_internal_metadata_owner_switch_batch.py`

The runner emits per-route default blocked evidence. It does not switch route ownership, change production_compat, remove fallback, execute timers, run automation, send outbound messages, or perform migrations.

## Per-route Requirements

Each selected route family must retain:

- owner_switch_execution_authorized_default: false
- fallback_retained: true
- production_compat_unchanged: true
- shadow_compare_required: true
- rollback_required: true
- execution_forbidden: true
- outbound_send_forbidden: true

## Production Behavior

Production behavior is unchanged. This PR only extends the Phase 6C evidence pattern to a batch readiness matrix.

## Fallback Behavior

Fallback is retained for every selected route family. Fallback removal remains forbidden.

## Business Continuity

Daily production use remains untouched. The batch runner provides evidence scaffolding for later owner-reviewed canary decisions.

## Business Value

The batch turns the task-groups pattern into a reusable internal metadata route-family framework while keeping higher-risk execution and external side-effect routes out of scope.

## Architecture Boundary

Docs, YAML, checker, tests, phase state, autopilot policy, and standalone evidence runner only. Runtime routers, production_compat, legacy Flask, deployment config, migrations, timers, automation execution, and external adapters remain untouched.

## Safety / Non-goals

- no broad wildcard production_compat change
- no fallback removal
- no default switch
- no timer / automation execution
- no outbound send
- no external live call
- no destructive migration
- no delete_ready

## Verification

- `python3 tools/check_phase6d_internal_metadata_owner_switch_batch.py --output-md /tmp/phase6d_internal_metadata_owner_switch_batch.md --output-json /tmp/phase6d_internal_metadata_owner_switch_batch.json`
- `python3 -m pytest tests/test_phase6d_internal_metadata_owner_switch_batch.py -q`
- `python3 tools/run_phase6d_internal_metadata_owner_switch_batch.py --output-json /tmp/phase6d_internal_metadata_owner_switch_batch_default.json`
- `python3 -m py_compile tools/check_phase6d_internal_metadata_owner_switch_batch.py tools/run_phase6d_internal_metadata_owner_switch_batch.py tools/check_autonomous_development_loop.py tools/check_automerge_eligibility.py tools/run_codex_autopilot_tick.py tests/test_phase6d_internal_metadata_owner_switch_batch.py`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py -q`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / Rollback

Risk is low because this PR is evidence tooling only. Rollback is reverting this PR.

## Autopilot Decision

Autopilot may record Phase 6D batch readiness tooling as complete. It must not execute owner switch, production_compat change, fallback removal, timer/run-due, automation execution, outbound send, external live calls, or destructive migration.

## Next Bundle Recommendation

- next: phase_6e_internal_owner_switch_acceptance_bundle

## Baseline Blockers

- Existing legacy facade growth freeze baseline direct legacy imports may still be reported.
- Local architecture skill compliance may be blocked by missing local `yaml` dependency; record that as environment blocker, not a pass.

## PR Lifecycle

This PR is complete only after it is merged into main and main contains the merge commit, or after an exact blocker/close reason is recorded.
