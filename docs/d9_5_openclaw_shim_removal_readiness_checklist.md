# D9.5 OpenClaw Shim Removal Readiness Checklist

Allowed status values: `pending`, `available`, `needs_manual_review`, `blocked`.

| check_item | required | current_status | evidence | blocker_if_missing | owner | notes |
| --- | --- | --- | --- | --- | --- | --- |
| `openclaw_service/` still exists | true | available | `openclaw_service/` | yes | migration owner | D9.5 does not remove the shim |
| `openclaw_service/__init__.py` still exists | true | available | shim file | yes | migration owner | contains `LEGACY_COMPATIBILITY_SHIM` |
| `legacy_flask/openclaw_legacy/` exists | true | available | archive package | yes | migration owner | D9.4 archive package retained |
| D9.1 import freeze pass | true | available | D9.1 checker | yes | migration owner | new runtime imports remain blocked |
| D9.4 move checker pass | true | available | D9.4 checker | yes | migration owner | move-with-shim state remains stable |
| D7.7 adapter checker pass | true | available | D7.7 checker | yes | MCP owner | proves adapter boundary remains available |
| no AI-CRM Next runtime import | true | available | AST/static scan | yes | Next owner | `aicrm_next/**` must not import shim |
| no production config dependency | true | available | dirty diff and reference scan | yes | release owner | no deploy/nginx/systemd dependency |
| no deploy/systemd dependency | true | needs_manual_review | final reference scan | yes | release owner | must be captured before deletion PR |
| no runtime log hits during observation window | true | pending | observation report | yes | platform owner | must be zero for agreed window |
| rollback plan exists | true | available | D9.5 plan rollback section | yes | migration owner | git revert path required |
| human signoff exists | true | pending | signoff record | yes | release owner | required before deletion PR merge |
| deletion PR prepared but not merged | true | pending | future D9.5.2 PR | yes | migration owner | D9.5.0 planning only |
| D9.5.1 final reference scan completed | true | available | `docs/d9_5_1_openclaw_final_reference_scan_evidence.md` | yes | migration owner | local repository scan is complete |
| D9.5.1 observation evidence captured | true | pending | `docs/d9_5_1_openclaw_observation_evidence_report.md` | yes | platform owner | production observation remains unavailable in this environment |
