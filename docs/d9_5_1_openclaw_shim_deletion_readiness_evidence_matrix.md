# D9.5.1 OpenClaw Shim Deletion Readiness Evidence Matrix

Allowed status values: `available`, `pending`, `needs_manual_review`, `blocked`.

| delete_gate | required | current_status | evidence | blocker_if_missing | decision | notes |
| --- | --- | --- | --- | --- | --- | --- |
| D9.1 import freeze PASS | true | available | D9.1 checker regression | yes | pass_for_planning | Must remain green before any deletion proposal. |
| D9.4 move checker PASS | true | available | D9.4 checker regression | yes | pass_for_planning | Confirms archive package and shim still behave as expected. |
| final reference scan completed | true | available | `docs/d9_5_1_openclaw_final_reference_scan_evidence.md` | yes | pass_for_planning | Repository scan is complete for this round. |
| no AI-CRM Next runtime import | true | available | AST scan for `aicrm_next/` and experiments mirror | yes | pass_for_planning | Both runtime roots report zero import hits. |
| no deploy or production dependency | true | available | targeted `deploy/`, `.github/`, and `scripts/` scans | yes | pass_for_planning | No targeted deploy/script hits were found. |
| no runtime shim import hits during observation window | true | pending | production/runtime logs | yes | not_ready | Requires real observation-window evidence. |
| no production logs hit shim | true | pending | production app logs | yes | not_ready | Not available in this local environment. |
| D7.7 adapter path handles MCP/OpenClaw workloads | true | needs_manual_review | D7.7 checker plus future workload evidence | yes | not_ready | Checker availability is not production workload evidence. |
| rollback no longer needs shim | true | pending | rollback owner signoff | yes | not_ready | Rollback dependence must be explicitly retired. |
| human signoff | true | pending | signoff record | yes | not_ready | Required before deletion PR merge. |
| backup / git revert plan exists | true | available | D9.5 rollback section | yes | pass_for_planning | Plan exists; deletion PR would still need approval. |
| deletion PR prepared but not merged | true | pending | future D9.5.2 PR | yes | not_ready | D9.5.1 does not prepare or merge a deletion PR. |
| D9.5.2 deletion blocked summary exists | true | available | `docs/d9_5_2_openclaw_shim_deletion_blocked_summary.md` | yes | pass_for_planning | D9.5.2 records deletion candidate false. |
| D9.5.2 observation collection runbook exists | true | available | `docs/d9_5_2_openclaw_observation_collection_runbook.md` | yes | pass_for_planning | Real observation evidence remains pending. |
| D9.5.2 deletion PR preflight checklist exists | true | available | `docs/d9_5_2_openclaw_deletion_pr_preflight_checklist.md` | yes | pass_for_planning | Checklist blocks PR preparation until evidence exists. |

## Readiness Decision

- Current status: `pending`.
- Deletion PR candidate: false.
- Missing evidence: operational observation logs, shim hit count, production app log proof, MCP/OpenClaw workload evidence, rollback independence, and human signoff.
- D9.5.2 status: `blocked_pending_observation_evidence`.
