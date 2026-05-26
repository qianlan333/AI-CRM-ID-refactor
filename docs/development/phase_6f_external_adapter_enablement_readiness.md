# Phase 6F External Adapter Enablement Readiness

## Status

- phase_6f_external_adapter_enablement_readiness
- bundle type: phase_6f_external_adapter_enablement_readiness_bundle
- readiness and candidate selection only
- no live external enablement
- no production owner switch
- production_compat unchanged
- fallback retained
- no timer / automation execution
- no outbound send
- no payment capture / refund / settlement
- no OAuth callback cutover
- no destructive migration
- delete_ready false

## Phase 5 Handoff

Phase 5 completed the external adapter families as live-capability tooling under explicit gates. Family acceptance is complete for WeCom tags, WeCom customer contact callback, OAuth identity, media upload / media library, payment / commerce, OpenClaw / MCP / AI assist, and questionnaire external submit / tag writeback edge. Production canary evidence remains separate, default live external calls remain disabled, production owner switch remains unexecuted, fallback remains retained, production_compat remains unchanged, and delete_ready remains false.

## Candidate Inventory

| family | route family | status | risk | Phase 6G recommendation |
| --- | --- | --- | --- | --- |
| Media upload / media library | `/api/admin/image-library*` | selected for low-risk default-blocked tooling | medium | selected |
| WeCom tags | `/api/admin/wecom/tags*` | selected for low-risk default-blocked tooling | medium | selected |
| OpenClaw / MCP / AI assist | `/mcp` | selected for low-risk default-blocked tooling | medium | selected |
| Payment / commerce | `/api/admin/wechat-pay*` | excluded from first batch | high | defer; no money movement |
| OAuth identity | `/api/h5/wechat/oauth*` | excluded from first batch | high | defer; no callback cutover |
| WeCom customer contact callback | `/wecom/external-contact/callback` | excluded from first batch | high | defer; callback ownership and identity mapping |
| Questionnaire external submit / tag writeback edge | `/api/h5/questionnaires*` | excluded from first batch | high | defer; public entry, identity, and tag writeback |

## First Phase 6G Candidates

The selected first low-risk external adapter enablement tooling candidates are media upload / media library, WeCom tags, and OpenClaw / MCP / AI assist. They already have Phase 5 gated live-capability evidence and can be represented with default-blocked enablement gates, owner approval, config review, rollback requirements, and shadow/dry-run evidence without default live calls.

## Deferred Families

Payment / commerce remains deferred because real payment capture, refund, or settlement requires higher approval. OAuth identity remains deferred because production callback cutover is high risk. WeCom customer contact callback remains deferred because callback ownership and identity mapping need owner review. Questionnaire external submit remains deferred because public entry, identity, and tag writeback need additional acceptance before any live enablement path.

## Production Behavior

Production behavior is unchanged. No live external call is enabled by default, no production route owner switch occurs, and no production_compat behavior changes.

## Fallback Behavior

Fallback remains retained for every family.

## Business Continuity

Daily production behavior remains on the current path. This PR only converts Phase 5 accepted external adapter families into a Phase 6 candidate pool and selects the first default-blocked tooling batch.

## Business Value

Owners get a clear risk-ranked enablement pool: three families can proceed to default-blocked controlled tooling, while high-risk payment, OAuth, callback, and public-submit surfaces stay blocked.

## Architecture Boundary

Docs, YAML, checker, tests, phase state, and autopilot policy only. No runtime routing, production_compat, fallback, deployment config, migrations, timers, external live calls, payment behavior, OAuth callbacks, or legacy imports are changed.

## Safety / Non-goals

- no default-on live external call
- no uncontrolled external call
- no production owner switch
- no production_compat behavior change
- no fallback removal or narrowing
- no timer / automation execution
- no outbound send
- no payment capture / refund / settlement
- no OAuth callback cutover
- no destructive migration
- no delete_ready

## Verification

- `python3 tools/check_phase6f_external_adapter_enablement_readiness.py --output-md /tmp/phase6f_external_adapter_enablement_readiness.md --output-json /tmp/phase6f_external_adapter_enablement_readiness.json`
- `python3 -m pytest tests/test_phase6f_external_adapter_enablement_readiness.py -q`
- `python3 -m py_compile tools/check_phase6f_external_adapter_enablement_readiness.py tools/check_autonomous_development_loop.py tools/check_automerge_eligibility.py tools/run_codex_autopilot_tick.py tests/test_phase6f_external_adapter_enablement_readiness.py`
- `python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json`
- `python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py -q`
- `python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json`
- `python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json`
- `git diff --check`

## Risk / Rollback

Risk is low because this is readiness and candidate selection only. Rollback is reverting this PR.

## Autopilot Decision

Autopilot may record Phase 6F readiness complete and recommend Phase 6G. It must not enable live external calls, execute owner switch, change production_compat, remove fallback, trigger timer/run-due/automation execution, send outbound traffic, perform payment movement, cut over OAuth callbacks, or set delete_ready.

## Next Bundle Recommendation

- next: phase_6g_low_risk_external_adapter_enablement_tooling_bundle

## Baseline Blockers

- Existing legacy facade growth freeze baseline direct legacy imports may still be reported.
- Local architecture skill compliance may be blocked by missing local `yaml` dependency; record that as environment blocker, not a pass.

## PR Lifecycle

This PR is complete only after it is merged into main and main contains the merge commit, or after an exact blocker/close reason is recorded.
