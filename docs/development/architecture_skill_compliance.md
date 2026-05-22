# Architecture Skill Compliance

`tools/check_architecture_skill_compliance.py` turns the AI-CRM Next
Architecture Skill into a PR guardrail. It is intentionally conservative: it
does not prove production readiness, and it does not authorize runtime,
deployment, external-call, or legacy fallback changes.

## What It Blocks

- live `openclaw_service/` paths or `openclaw_service` imports;
- direct database drivers or raw SQL in `aicrm_next/frontend_compat`;
- `api.py` importing another context's `repo.py` or `service.py`;
- production_compat catch-all routes that are not covered by the route ownership manifest;
- unauthorized status markers such as `production_ready`, `delete_ready`, or `production_approved`;
- non-archive docs describing fixture/local_contract data as production data;
- missing Codex PR template sections or missing completion-check guidance.

## Allowed Context

Historical, deleted, blocked, and retirement references are allowed in archive
or retirement docs and in checker tests. The checker is meant to catch new live
architecture drift, not erase the project's migration history.

## Command

```bash
.venv/bin/python tools/check_architecture_skill_compliance.py \
  --output-md /tmp/architecture_skill_compliance.md \
  --output-json /tmp/architecture_skill_compliance.json
```
