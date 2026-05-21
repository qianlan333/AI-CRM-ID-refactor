# D9.5.3 OpenClaw Observation Evidence Addendum

## Scope

This addendum records the first production-host observation pass and the operator confirmation that OpenClaw-named cron/timer jobs are historical names only. It does not delete `openclaw_service/`, does not prepare a deletion PR, does not modify production configuration, does not call OpenClaw or MCP external services, and does not cut traffic.

## Host Observation

| evidence_item | observed_value |
| --- | --- |
| host | `150.158.82.186` |
| observed_at | `2026-05-22T00:38:39+08:00` |
| app process cwd | `/home/ubuntu/releases/aicrm-laohuang-20260426144637` |
| public nginx upstream | `127.0.0.1:5001` |
| app command | `/home/ubuntu/venvs/openclaw/bin/python app.py run` |
| `openclaw_service` runtime log hits | 0 in checked app/campaign/OpenClaw-named logs |
| `openclaw_service` import scan in release runtime code | no runtime import found; hits are docs/tests/checkers/static references |

## OpenClaw-Named Job Classification

Operator confirmation:

```text
These OpenClaw-named cron/timer jobs are historical names; the retained active path is API tasks.
```

| job_or_log | observed_command_or_path | classification | shim_dependency |
| --- | --- | --- | --- |
| `openclaw-reply-monitor-capture.log` | local API call to `127.0.0.1:5001/api/admin/automation-conversion/reply-monitor/capture` | historical OpenClaw name; active API task | none observed |
| `openclaw-reply-monitor-dispatch.log` | local API call to `127.0.0.1:5001/api/admin/automation-conversion/reply-monitor/run-due` | historical OpenClaw name; active API task | none observed |
| `/etc/cron.d/openclaw-campaign-run-due` | local API call to `127.0.0.1:5001/api/admin/cloud-orchestrator/campaigns/run-due` | historical OpenClaw name; active API task | none observed |
| `openclaw-broadcast-queue-worker.timer` | runs `scripts/run_broadcast_queue_worker.py` | historical OpenClaw name; API/maintenance task | none observed |
| `openclaw-automation-conversion-due-runner.timer` | runs `scripts/run_automation_conversion_due_jobs.py` | historical OpenClaw name; maintenance task currently failing with `No module named 'scripts'` | none observed |

## Log Evidence Summary

| source | `openclaw_service` hits | notes |
| --- | ---: | --- |
| `/home/ubuntu/极简-crm.log` | 0 | one unrelated `No module named 'uvicorn'` startup error was observed |
| `/home/ubuntu/logs/campaign-run-due.log` | 0 | API task output remained JSON-shaped |
| `/home/ubuntu/openclaw-cron.log` | 0 | unrelated `No module named 'scripts'` errors were observed |
| `/home/ubuntu/openclaw-reply-monitor-capture.log` | 0 | historical name only |
| `/home/ubuntu/openclaw-reply-monitor-dispatch.log` | 0 | historical name only |

## Decision

- Deletion candidate: false.
- `openclaw_service/` shim retained: true.
- Active production surface: API tasks.
- OpenClaw-named jobs: historical names, not proof of `openclaw_service` shim usage.
- Remaining evidence before deletion PR: full agreed observation window, production log archive, rollback independence confirmation, and final human signoff.
