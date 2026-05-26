# Phase 6H Production Compat Exact-Route Narrowing Readiness

## Status

- phase_6h_production_compat_exact_route_narrowing_readiness
- bundle type: phase_6h_production_compat_exact_route_narrowing_readiness_bundle
- readiness / shadow compare only
- proposed exact-route narrowing only
- no production_compat behavior change
- no wildcard narrowing
- no manifest write by default
- fallback retained
- no production owner switch
- no live external call
- no timer / automation execution
- no outbound send
- no destructive migration
- delete_ready false

## Scope

Phase 6H builds a shadow compare and rollback evidence package for exact production_compat narrowing candidates. It does not change routing behavior, does not remove fallback, and does not write the route ownership manifest. Candidate routes are limited to internal metadata routes accepted in Phase 6E and low-risk external adapter tooling routes from Phase 6G.

## Candidate Exact Routes

| source | method | exact route | reason |
| --- | --- | --- | --- |
| internal accepted | GET | `/api/admin/automation-conversion/task-groups` | accepted internal metadata candidate |
| internal accepted | GET | `/api/admin/automation-conversion/workflow-nodes` | accepted internal metadata candidate |
| external low-risk tooling | GET | `/api/admin/image-library` | media library list route, no upload |
| external low-risk tooling | GET | `/api/admin/image-library/facets` | media library metadata route |
| external low-risk tooling | GET | `/api/admin/wecom/tags` | WeCom tag list/read route |
| external low-risk tooling | GET | `/api/admin/wecom/tags/live/gate` | gate inspection route, no live tag write |
| external low-risk tooling | GET | `/mcp` | MCP metadata route, no tool call |

## Excluded Routes

- Payment / commerce
- OAuth callback
- WeCom contact callback
- tasks/workflows execution-adjacent routes
- timer/run-due
- outbound send
- public submit routes until family acceptance plus owner review
- wildcard production_compat entries

## Shadow Compare Runner

`tools/run_phase6h_production_compat_exact_route_shadow_compare.py` outputs proposed narrowing evidence only. By default it:

- does not change production_compat
- does not write manifest
- does not remove fallback
- does not switch owner
- does not execute live external calls
- outputs `proposed_narrowing_only`

## Rollback Plan

Rollback for any future narrowing must retain the current production_compat fallback and remove/disable only the exact-route narrowing proposal. No destructive migration, fallback deletion, wildcard narrowing, timer execution, automation execution, outbound send, or live external call can be part of rollback.

## Production Behavior

Production behavior is unchanged.

## Fallback Behavior

Fallback remains retained for every route.

## Business Continuity

The current production path remains in force. This PR only makes the next compatibility narrowing decision reviewable at exact-route granularity.

## Business Value

Owners get a small route-level candidate set and evidence shape for future exact-route narrowing without touching broad wildcard behavior.

## Architecture Boundary

Docs, YAML, checker, tests, phase state, autopilot policy, and a default evidence runner only. No production_compat runtime files, route ownership manifest, fallback code, runtime route owner, migration, deployment config, timer, external adapter, payment, OAuth callback, or legacy runtime path is changed.

## Safety / Non-goals

- no actual production_compat behavior change
- no wildcard narrowing
- no fallback removal
- no owner switch
- no live external call
- no execution/send
- no timer/run-due
- no payment
- no OAuth callback cutover
- no destructive migration
- no delete_ready

## Verification

- `python3 tools/check_phase6h_production_compat_exact_route_narrowing_readiness.py --output-md /tmp/phase6h_production_compat_exact_route_narrowing_readiness.md --output-json /tmp/phase6h_production_compat_exact_route_narrowing_readiness.json`
- `python3 -m pytest tests/test_phase6h_production_compat_exact_route_narrowing_readiness.py -q`
- `python3 tools/run_phase6h_production_compat_exact_route_shadow_compare.py`
- `python3 -m py_compile tools/check_phase6h_production_compat_exact_route_narrowing_readiness.py tools/run_phase6h_production_compat_exact_route_shadow_compare.py tools/check_autonomous_development_loop.py tools/check_automerge_eligibility.py tools/run_codex_autopilot_tick.py tests/test_phase6h_production_compat_exact_route_narrowing_readiness.py`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py -q`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / Rollback

Risk is low because this PR is readiness and evidence only. Rollback is reverting this PR.

## Autopilot Decision

Autopilot may record Phase 6H readiness complete and recommend Phase 6I acceptance. It must not change production_compat behavior, narrow wildcards, remove fallback, switch owner, execute live external calls, trigger timer/run-due/automation execution, send outbound traffic, or set delete_ready.

## Next Bundle Recommendation

- next: phase_6i_external_enablement_and_compat_readiness_acceptance_bundle

## Baseline Blockers

- Existing legacy facade growth freeze baseline direct legacy imports may still be reported.
- Local architecture skill compliance may be blocked by missing local `yaml` dependency; record that as environment blocker, not a pass.

## PR Lifecycle

This PR is complete only after it is merged into main and main contains the merge commit, or after an exact blocker/close reason is recorded.
