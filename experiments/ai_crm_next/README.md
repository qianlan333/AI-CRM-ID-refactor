# AI-CRM Next Experiment

`experiments/ai_crm_next` is an isolated backend rewrite experiment for AI-CRM.

The product goal is strict parity with the current AI-CRM product capability and frontend experience. The backend is a new FastAPI modular monolith; the old Flask backend is reference material only and is not imported at runtime.

## Principles

- Frontend parity is mandatory. Current templates, navigation, interactions, tables, filters, drawers, modals, button placement, visual style, and information density are the baseline.
- Backend architecture is rewritten around explicit bounded contexts and application use cases.
- This package must not import `wecom_ability_service.*` or `openclaw_service.*`.
- First slice is contract-ready for customer read model, MCP, identity resolution, and User Ops stubs.

## Run Tests

```bash
.venv/bin/python -m pytest -q
```

If the local virtualenv does not exist yet, create it and install the test dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
```

If the virtualenv is already activated, `python -m pytest -q` is equivalent.

## Implemented First Slice

- `GET /health`
- `GET /api/system/health`
- `GET /api/customers`
- `GET /api/customers/{external_userid}`
- `GET /api/customers/{external_userid}/timeline`
- `GET /api/admin/user-ops/overview`
- `GET /api/admin/user-ops/list`
- `POST /api/admin/user-ops/batch-send/preview`
- `POST /api/admin/user-ops/batch-send/execute`
- `GET /api/admin/user-ops/send-records`
- `GET /mcp`
- `POST /mcp`

## Bounded Contexts

- `platform_foundation`
- `integration_gateway`
- `identity_contact`
- `customer_read_model`
- `ops_enrollment`
- `questionnaire`
- `automation_engine`
- `ai_assist`
- `frontend_compat`
