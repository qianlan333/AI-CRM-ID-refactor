# D9.5 OpenClaw Service Shim Removal Plan

## Current State

- Legacy OpenClaw marker files are represented under `legacy_flask/openclaw_legacy/`.
- `openclaw_service/` still exists as a D9.4 compatibility shim.
- `openclaw_service/__init__.py`, `openclaw_service/README.md`, and `openclaw_service/LEGACY_FROZEN.md` remain in place.
- AI-CRM Next does not import `openclaw_service`.
- D7.7 MCP/OpenClaw adapter boundary remains the primary architecture path.
- D9.5 is planning only and does not delete the shim.

## Why The Shim Cannot Be Deleted Immediately

- An operational observation window has not been completed.
- Runtime logs have not yet proven zero `openclaw_service` shim hits.
- Final docs/scripts/deploy reference classification is not complete.
- D7.7 MCP/OpenClaw adapter behavior still needs stable staging or production-like evidence.
- Rollback may still need the compatibility shim during the observation period.
- Human signoff and a git-revert rollback path are not yet recorded.

## Operational Observation Window

| window_name | duration | environment | signals_to_monitor | expected_zero_hits | allowed_exceptions | owner | evidence_path |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OpenClaw shim runtime import observation | agreed operational window | staging and production-like runtime | runtime import hit count, logs mentioning `openclaw_service`, import-freeze checker output | runtime shim imports | docs/checker/test static references | platform owner plus migration owner | `/tmp/d9_5_openclaw_runtime_import_observation.md` |
| MCP/OpenClaw adapter stability observation | agreed operational window | staging or production-like MCP surface | MCP context tool error rate, adapter mode, OpenClaw bridge fake/real mode status | unexpected fallback usage | fake/staging-disabled adapter metadata | MCP owner | `/tmp/d9_5_mcp_openclaw_adapter_observation.md` |
| Runbook/deploy reference observation | before deletion PR | docs, scripts, deploy, and runbooks | deploy/runbook references to `openclaw_service`, systemd/nginx references, plugin docs references | deploy/runtime dependency hits | archive notes and retirement docs | release owner | `/tmp/d9_5_openclaw_reference_scan.md` |

## Final Removal Gate

Before the `openclaw_service/` shim can be removed, all of the following must be true:

- D9.1 import freeze PASS.
- D9.4 move checker PASS.
- Final reference scan shows only planned docs/tests/archive references.
- No AI-CRM Next runtime import exists.
- No runtime log hits the shim during the agreed observation window.
- No production deploy, systemd, nginx, runbook, or plugin path depends on the shim.
- D7.7 adapter path handles MCP/OpenClaw workloads within the approved fake/staging/production policy.
- Rollback no longer needs the shim.
- Human signoff exists.
- Backup and git revert plan exists.

## Removal Phases

| phase | scope | status |
| --- | --- | --- |
| D9.5.0 | planning only; write plan, checklist, reference scan plan, checker, tests | current |
| D9.5.1 | final reference scan and observation evidence capture | reference_scan_completed; pending_observation_evidence |
| D9.5.2 | deletion blocked summary and observation collection package | blocked_pending_observation_evidence |
| D9.5.3 | remove shim after signoff | future |
| D9.5.4 | post-delete monitoring | future |

## Rollback

D9.5 does not change runtime behavior. If a later phase removes the shim, rollback must be a normal git revert that restores `openclaw_service/__init__.py`, `openclaw_service/README.md`, and `openclaw_service/LEGACY_FROZEN.md`.

Rollback owner: migration owner with platform owner approval.

Rollback triggers:

- any runtime import error from old `openclaw_service` callers;
- any MCP/OpenClaw context regression attributed to shim removal;
- any deploy/runbook dependency found after removal;
- any missing D7.7 adapter boundary evidence.

Production configuration remains unchanged by D9.5.

## D9.5.1 Evidence Status

- Final repository reference scan evidence: captured in `docs/d9_5_1_openclaw_final_reference_scan_evidence.md`.
- Observation evidence report: captured in `docs/d9_5_1_openclaw_observation_evidence_report.md`.
- Deletion readiness evidence matrix: captured in `docs/d9_5_1_openclaw_shim_deletion_readiness_evidence_matrix.md`.
- Current observation status: `pending_observation_evidence`.
- Shim deletion PR candidate: false.

D9.5.1 does not change runtime behavior. `openclaw_service/` and its shim files remain in place.

## D9.5.2 Blocked Status

- D9.5.2 status: `blocked_pending_observation_evidence`.
- Deletion candidate: false.
- `openclaw_service/` shim retained: true.
- Deletion PR prepared: false.
- Remaining gate: production or production-like observation evidence, rollback independence, and human signoff.

D9.5.2 records the blocked state and observation collection runbook. It does not authorize a deletion PR.
