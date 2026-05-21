# D8.1 Legacy Fallback Route Lockdown Plan

Status: planning/readiness only.

D8.1 describes how legacy fallback routes could later be locked down after D7 real replacement evidence exists. This document does not register a runtime guard, does not return 410 responses, and does not modify Flask route registration.

## Scope

| Item | D8.1 planning decision |
| --- | --- |
| Route/fallback inventory | Document protected fallback categories and future lockdown candidates. |
| Runtime enforcement | Not implemented in this phase. |
| `legacy_lockdown` module | Not created in this phase. |
| Legacy Flask route registration | Unchanged. |
| Legacy fallback availability | Preserved for explicit fallback usage. |

## Future Lockdown Prerequisites

- D7 real external replacement evidence exists for the specific capability.
- Production observation window shows no legacy route hits for the candidate route.
- Rollback no longer depends on the route or the Flask shell.
- Deploy/systemd path can run Next-only with rollback proof.
- Human signoff approves the specific route/fallback lockdown.

## Planning Rules

- Keep payment, OAuth, WeCom, OpenClaw, archive, contacts, identity, media upload, workflow, agent, and MCP fallback routes available while blockers remain.
- Use route-owner telemetry before any future route lockdown.
- Treat D8.1 as a planning matrix and checker only; implementation belongs to a later approved phase.

## Verification

D8.1 planning is verified by `tools/check_d8_1_legacy_fallback_route_lockdown.py` and `tests/test_d8_1_legacy_fallback_route_lockdown.py`. The checker validates document alignment and safety wording only.
