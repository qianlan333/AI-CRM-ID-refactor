# D8 Legacy Shell Allowed Fallback Matrix

Allowed fallback means emergency or explicitly invoked fallback only. It does not mean production ownership and does not approve real external behavior.

| fallback_area | allowed | reason | next_replacement_status | retirement_condition | risk |
| --- | --- | --- | --- | --- | --- |
| legacy run command | yes | Explicit rollback may still need `python3 app.py run-legacy` or `python3 legacy_flask_app.py run` | Next default runtime is active | Production Next handles all routes for agreed window and rollback no longer needs Flask | Accidental operator use if command ownership is unclear |
| legacy init-db command | yes | Existing deploy and maintenance scripts may still invoke legacy-compatible DB init aliases | Future Next maintenance commands not completed | Next-only DB init/backfill/maintenance commands exist and deploy workflow is updated | Wrong database initialization path during incident recovery |
| emergency rollback app factory | yes | Rollback owner remains legacy Flask fallback during D8.0 | Next app factory is default but rollback proof still depends on legacy | Human-approved rollback retirement after route and external cutover evidence | Fallback can mask missing Next behavior if used outside incident process |
| old external write fallback | yes | D7 fake contracts exist but real writes are not production cut over | D7.1-D7.7 fake/staging-disabled contracts | Real write/external adapter evidence, audit, idempotency, and rollback proof exist | Duplicate writes or external side effects if used unintentionally |
| old payment fallback | yes | Payment checkout/notify/return still need provider evidence | D7.4 fake Product/Payment contracts | Provider sandbox/live evidence, reconciliation, callback replay guard, and rollback proof exist | Payment mismatch, duplicate notification, or reconciliation drift |
| old OAuth fallback | yes | Real OAuth has not completed production cutover | D7.2 fake OAuth contract | Provider-approved OAuth callback evidence, session replay guard, and rollback proof exist | Identity mismatch or callback replay |
| old OpenClaw fallback | yes | Real OpenClaw/MCP bridge has not completed production cutover | D7.5/D7.7 fake OpenClaw/MCP contracts | OpenClaw/MCP compatibility evidence, token policy, retry/replay guard, and signoff exist | Duplicate pushes, stale context, or token exposure |
| archive sync fallback | yes | Real archive and contacts sync are not production cut over | D7.6 fake archive/contacts/identity/projection contracts | Archive cursor lock, contacts merge policy, identity conflict proof, and projection replay proof exist | Cursor replay, duplicate contacts, or stale customer context |
| operational diagnostics | yes | Legacy checkers/tests/docs still provide migration evidence | D8 checker plus Next smoke/parity tools | Next diagnostics replace legacy diagnostics and evidence is archived | Diagnostics may import fallback code and be mistaken for runtime dependency |

## Guardrails

- Allowed fallback is not production ownership.
- Fallback must be explicit, audited by operations when used, and retired through a later D8 phase.
- D8.0 does not enable real WeCom, OAuth, Payment, OpenClaw, MCP, cloud, archive, contacts, identity, or projection behavior.
- D8.1 adds route lockdown planning and checker coverage for retired readonly owner routes. It does not enforce route blocking in runtime code; D8.2 is the future enforcement implementation phase.
