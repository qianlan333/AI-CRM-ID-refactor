# Server Readonly Evidence Template

## Summary

- Server:
- Base URL:
- Collection time:
- Release SHA:
- Overall ok:
- Blockers:
- Warnings:

## Business Impact

Describe whether live admin, customer, questionnaire, sidebar, and route owner
surfaces are available enough to continue deployment or migration planning.

## Evidence Classification

- Local checker evidence: no / yes
- Server readonly evidence: yes
- Production canary evidence: no / yes

Server readonly evidence is not production cutover approval.

## Runtime Identity

- `/health` status:
- `/api/system/health` status:
- `X-AICRM-App`:
- `X-AICRM-Release-SHA`:
- `database_mode`:
- `production_data_ready`:

## Route Owner Results

| Route | Status | Route owner | Runtime owner | Release SHA | Fixture markers |
| --- | --- | --- | --- | --- | --- |
| `/health` | | | | | |
| `/api/system/health` | | | | | |
| `/admin` | | | | | |
| `/admin/customers` | | | | | |
| `/admin/questionnaires` | | | | | |
| `/admin/automation-conversion` | | | | | |
| `/admin/jobs` | | | | | |
| `/sidebar/bind-mobile` | | | | | |
| `/api/customers?limit=1` | | | | | |
| `/api/admin/questionnaires?limit=1` | | | | | |

## Safety Flags

- safe_to_enable_timers: false
- safe_to_enable_real_external_calls: false
- safe_to_remove_legacy_fallback: false

## Blockers

- None recorded.

## Warnings

- None recorded.

## Next Action

- Record the follow-up owner and rollback decision here.
