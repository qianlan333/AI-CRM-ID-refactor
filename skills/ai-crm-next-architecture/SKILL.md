---
name: ai-crm-next-architecture
description: Use before any AI-CRM coding task. Enforces the AI-CRM Next FastAPI modular monolith architecture boundaries, route ownership checks, production data safety, external-call guardrails, and PR verification format.
---

# AI-CRM Next Architecture

Use this skill before changing code, docs, routes, checkers, tests, or runtime
behavior in the AI-CRM repository.

The canonical rules live in:

- `docs/development/codex_architecture_operating_memory.md`
- `docs/development/ai_crm_next_architecture_skill.md`

Treat those documents as the source of truth. This repo-local `SKILL.md` exists
so agents that discover `skills/*/SKILL.md` packages can recognize and invoke
the architecture guardrail directly after cloning or downloading this
repository.

## Required Preflight Reading

Before every AI-CRM development task, read and follow these files:

1. `docs/development/codex_architecture_operating_memory.md`
2. `docs/development/ai_crm_next_architecture_skill.md`
3. `docs/route_ownership/production_route_ownership_manifest.yaml`
4. `docs/development/legacy_replacement_backlog.yaml`

Do not start code, docs, route, checker, test, production_compat, runtime, or
business-route changes until this preflight has been completed.

## Start Every Task With These Questions

1. Which capability owner owns the task?
2. Which routes are affected?
3. Are those routes owned by Next, frontend_compat, production_compat, a legacy
   facade, or blocked?
4. Does the task touch production data?
5. Is there fixture/local_contract/demo data risk?
6. Does the task require real external calls?
7. Does the route ownership manifest need an update?
8. Which checker must be added or updated?
9. What is the rollback?

## Hard Boundaries

- Default runtime is AI-CRM Next FastAPI modular monolith.
- `app.py run` starts `aicrm_next.main:app`.
- Legacy Flask is only an explicit fallback and production compatibility facade.
- `wecom_ability_service/` is retained as legacy fallback.
- `openclaw_service/` and `legacy_flask/openclaw_legacy/` are deleted
  historical paths and must not be reintroduced.
- MCP/OpenClaw work must enter through the
  `aicrm_next.integration_gateway` adapter boundary.
- Real WeCom, Payment, OAuth, OpenClaw, MCP external calls, and timers stay
  blocked unless a task explicitly approves them with allowlist, audit,
  idempotency, rollback, and approval language.

## Layering Rules

- API / HTTP / frontend_compat only parse requests, call application
  query/command APIs, and render responses.
- Application orchestrates use cases.
- Domain contains only local context domain rules.
- Repositories own data access and do not casually read across contexts.
- Read models are readonly projections, not write logic.
- `integration_gateway` owns external protocols, adapters, MCP, payment, WeCom,
  OAuth, and legacy facades.
- `shared` / platform foundation owns runtime, configuration, DB provider,
  audit, idempotency, and common errors.

## Must Not Do

- Do not reintroduce deleted historical `openclaw_service/` paths or imports.
- Do not add raw SQL, psycopg, or SQLAlchemy use in `frontend_compat`.
- Do not let `api.py` import another context's `repo.py` or `service.py`
  directly.
- Do not describe fixture/local_contract/demo data as production data.
- Do not add production_compat catch-all behavior without route ownership
  manifest coverage.
- Do not use unauthorized status markers such as `production_ready`,
  `delete_ready`, or `production_approved`.
- Do not modify nginx/systemd/deploy production config unless explicitly
  approved.
- Do not present local checker output as production canary evidence.

## Required Checks Before Finish

Run the architecture compliance checker before finishing every Codex task:

```bash
.venv/bin/python tools/check_architecture_skill_compliance.py \
  --output-md /tmp/architecture_skill_compliance.md \
  --output-json /tmp/architecture_skill_compliance.json
```

Also run the task-specific tests/checkers named in the task prompt.

## PR Output Format

Every PR summary must include:

- Summary
- Architecture boundary
- Safety / non-goals
- Verification
- Risk / rollback
- Next action
