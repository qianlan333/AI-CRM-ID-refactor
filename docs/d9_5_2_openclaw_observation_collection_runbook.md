# D9.5.2 OpenClaw Observation Collection Runbook

This runbook describes how to collect the real evidence still missing after D9.5.1. Local repository checks are not a substitute for production or production-like observation records.

| evidence_item | environment | command_or_source | expected_result | duration_or_window | owner | blocker_if_missing | notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| runtime import hit count | production or production-like app runtime | import telemetry or runtime log query for `openclaw_service` | zero shim import hits | agreed observation window | platform owner | yes | not_available_in_local_environment |
| app logs grep `openclaw_service` | production app logs | log aggregation query or `grep openclaw_service` on approved log export | zero app log hits outside archived docs text | agreed observation window | platform owner | yes | not_available_in_local_environment |
| MCP/OpenClaw adapter logs | staging or production-like MCP surface | adapter telemetry for D7.7 MCP/OpenClaw boundary | workloads served through Next adapter boundary without shim fallback | agreed observation window | MCP owner | yes | not_available_in_local_environment |
| webhook logs | OpenClaw webhook gateway or deprecation record | webhook log query for OpenClaw push path | no unexpected legacy shim usage; webhook path validated or deprecated | agreed observation window | MCP owner | yes | not_available_in_local_environment |
| deploy references | repository and deployment runbooks | `rg "openclaw_service" deploy .github scripts` plus runbook review | zero deploy/script dependency | before deletion PR | release owner | yes | local repository scan currently reports zero targeted hits |
| D7.7 checker run | local and CI | `.venv/bin/python tools/check_d7_7_mcp_openclaw_adapter_contract.py ...` | PASS | before deletion PR | migration owner | yes | proves adapter contract remains available, not production workload evidence |
| D9.1 checker run | local and CI | `python3 tools/check_d9_1_openclaw_import_freeze.py --allowlist docs/d9_1_openclaw_import_allowlist.md ...` | PASS | before deletion PR | migration owner | yes | confirms runtime import freeze |
| D9.4 checker run | local and CI | `python3 tools/check_d9_4_openclaw_legacy_move.py ...` | PASS | before deletion PR | migration owner | yes | confirms archive package and shim state |
| D9.5.1 checker run | local and CI | `python3 tools/check_d9_5_1_openclaw_reference_scan.py ...` | PASS with pending observation until logs exist | before deletion PR | migration owner | yes | confirms reference scan and retained shim |
| human signoff | release approval record | approval comment, ticket, or signoff doc | explicit approval after evidence review | after observation window | release owner | yes | not_available_in_local_environment |
| historical OpenClaw-name confirmation | operator confirmation plus server read-only inspection | D9.5.3 addendum | OpenClaw-named cron/timer jobs classified as API tasks | before deletion PR | release owner | yes | captured in `docs/d9_5_3_openclaw_observation_evidence_addendum.md` |

## Local Environment Limitation

Production logs, runtime counters, webhook logs, and operational signoff are `not_available_in_local_environment`. They must be captured by the platform/release owners before any deletion PR is prepared.
