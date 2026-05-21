# Production Replacement Route

This document records the production replacement path at the D8.5 planning gate. It is not a cutover instruction and does not authorize production execution.

## Current Route

| area | current production stance | replacement stance | evidence needed |
| --- | --- | --- | --- |
| Default runtime | AI-CRM Next by `python3 app.py run` | already default | runtime switch acceptance evidence |
| Legacy fallback | explicit `run-legacy` / `legacy_flask_app.py run` | retained for rollback | D8 phased retirement evidence |
| Legacy DB init | explicit legacy fallback commands retained | Alembic / Next migration runner planned | backup, dry-run, migration, rollback, and human signoff |
| Legacy cleanup commands | retained and manually reviewed | Next operator command planned | dry-run, backup, audit, approval |
| External adapters | fake/staging-disabled D7 contracts | production providers pending | provider evidence and rollback proof |

## D8.5 Production Safety

- No production database migration is executed.
- No production config is modified.
- No production traffic is cut over.
- No old write endpoint is executed.
- Legacy maintenance commands remain retained until replacement evidence and rollback signoff exist.
