# D9.6 OpenClaw Shim Physical Deletion Report

## Scope

D9.6 records the explicit owner-approved deletion of the OpenClaw compatibility shim and archive package after D9.5.2. The deletion is based on owner acceptance that the observation window is waived and that OpenClaw-named server jobs are historical names for API tasks.

## Owner Decision

Owner confirmation:

```text
OpenClaw is no longer in active use. The remaining OpenClaw-named cron/timer jobs are historical names; the active retained path is API tasks.
Delete the server-side OpenClaw-named jobs and the repository-side OpenClaw shim/archive package.
```

## Repository Deletion

Deleted paths:

- `openclaw_service/`
- `legacy_flask/openclaw_legacy/`

Not deleted:

- `legacy_flask/`
- `wecom_ability_service/`
- AI-CRM Next D7.7 MCP/OpenClaw adapter contract files

## Server Deletion

Host: `150.158.82.186`

Backup directory:

- `/home/ubuntu/backups/openclaw-retirement-20260522004443`

Removed server-side historical OpenClaw jobs:

- user crontab OpenClaw/reply-monitor/archive/backup entries
- `/etc/cron.d/openclaw-campaign-run-due`
- `openclaw-broadcast-queue-worker.timer`
- `openclaw-broadcast-queue-worker.service`
- `openclaw-automation-conversion-due-runner.timer`
- `openclaw-automation-conversion-due-runner.service`

Retained server-side service:

- `openclaw-wecom-postgres.service`

Reason: it appears to be the database/environment service, not the OpenClaw shim or OpenClaw-named API task runner. Removing it could affect the main application data path.

## Verification Summary

- Repository `openclaw_service/`: absent.
- Repository `legacy_flask/openclaw_legacy/`: absent.
- Server user crontab after deletion: empty.
- Server OpenClaw-named systemd unit files after deletion: only `openclaw-wecom-postgres.service` remains.
- Server `/etc/cron.d/openclaw-campaign-run-due`: absent.
- No production nginx or app process restart was performed by this deletion.
- No OpenClaw or MCP external service call was executed by this deletion.

## Rollback

Repository rollback:

- restore the deleted paths with `git revert` of the deletion commit or from the pre-deletion branch.

Server rollback:

- restore crontab and unit files from `/home/ubuntu/backups/openclaw-retirement-20260522004443`;
- run `sudo systemctl daemon-reload`;
- re-enable only the jobs explicitly approved by the owner.

## Final State

- `openclaw_service_deleted = true`
- `legacy_flask_openclaw_legacy_deleted = true`
- `server_openclaw_named_api_jobs_removed = true`
- `openclaw_wecom_postgres_service_retained = true`
- `real_openclaw_call_executed = false`
- `real_mcp_external_call_executed = false`
- `production_nginx_or_app_runtime_modified = false`
