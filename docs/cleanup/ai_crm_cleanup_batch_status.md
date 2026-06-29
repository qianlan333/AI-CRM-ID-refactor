# AI-CRM Cleanup Batch Status

Updated: 2026-06-29

This status ledger records the cleanup plan after the first hygiene batches. It
is intentionally scoped to repository hygiene, documentation, generated reports,
and read-only checks. It does not authorize runtime behavior changes, deploy
changes, production access, or external calls.

## Current State

| batch | status | evidence | next action |
|---|---|---|---|
| Batch 0 repo hygiene audit | done | `tools/audit_repo_hygiene.py`, `tests/test_repo_hygiene_audit.py`, `docs/cleanup/repo_hygiene_report.md`, `docs/cleanup/repo_hygiene_report.json` | Keep report-only; do not promote findings to CI fail without explicit approval. |
| Batch 1 agent entry docs and safety wording | done | `AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/development/ai_crm_next_architecture_skill.md`, `skills/ai-crm-next-architecture/SKILL.md` | Keep production connection details outside the public repo entry docs. |
| Batch 2 lint and hygiene guard expansion | done | `scripts/run_lint.py`, `docs/cleanup/route_inventory_consolidation_inventory.md`, `docs/cleanup/route_inventory_consolidation_inventory.json`, `tools/report_route_inventory_consolidation.py` | Continue with report-backed cleanup, not full Ruff style expansion. |
| Batch 3 experiment workspace inventory | progressed | `tools/report_experiments_inventory.py`, `tests/test_experiments_inventory_report.py`, `docs/cleanup/experiments_ai_crm_next_inventory.md`, `docs/cleanup/experiments_ai_crm_next_inventory.json`, `docs/archive/experiments_ai_crm_next/retired_tools.md`, `docs/archive/experiments_ai_crm_next/docs/remaining_work_queue.md` | Canary/readiness helpers and paired tests are retired; historical work queue is archived; use the generated inventory before retiring any remaining experiment-local parity tools. |
| Batch 4 Flask retirement | done | `tests/test_shared_flask_config_retirement.py`, `tests/test_wechat_oauth_client.py` | Keep `from flask`, `import flask`, and `current_app` out of runtime code. |
| Batch 5 fixture reset registry | done | `aicrm_next/fixture_reset_registry.py`, `tests/test_fixture_reset_registry.py` | Preserve reset order and keep router registration behavior unchanged. |
| Deprecated CLI noise | done | `app.py`, `tests/test_startup_entrypoint_next_only.py` | Keep removed-command errors table-driven until the CLI contract is formally deleted. |
| Tracked artifact policy | clean | `python3 tools/audit_repo_hygiene.py` reports zero issues and no tracked `artifacts/`, `.codex_artifacts/`, `tmp/`, `outputs/`, `dist/`, or `exports/` files are present. | Keep generated evidence under `docs/reports/`, `docs/archive/`, or `docs/cleanup/` only when intentionally reviewable. |

## Verified Boundaries

- No `aicrm_next/` runtime business logic is changed by this status document.
- No deploy/nginx/systemd files are changed.
- No production host, SSH alias, or command cookbook is reintroduced.
- No external WeCom, Payment, OAuth, OpenClaw, webhook, or MCP call is executed.
- Real WeCom External Effect execution remains limited to the approved PR #1505
  scope; Webhook, Payment, OAuth, OpenClaw, and MCP real execution remain blocked
  until separately approved with audit, idempotency, and rollback coverage.

## Useful Commands

```bash
python3 tools/audit_repo_hygiene.py
python3 tools/report_experiments_inventory.py \
  --summary-output docs/cleanup/experiments_ai_crm_next_inventory.md \
  --json-output docs/cleanup/experiments_ai_crm_next_inventory.json
python3 tools/report_route_inventory_consolidation.py \
  --summary-output docs/cleanup/route_inventory_consolidation_inventory.md \
  --json-output docs/cleanup/route_inventory_consolidation_inventory.json
```

## Recommended Next Batch

Do not delete `experiments/ai_crm_next` wholesale. The next safe batch is to use
the generated experiment inventory to evaluate the remaining experiment-local
helpers: `capture_frontend_screenshots.py`, `readonly_http_dual_run.py`,
`seed_old_flask_customer_sample.py`, and
`seed_old_flask_questionnaire_sample.py`. Retire each helper only with its paired
tests or keep it with an explicit current owner. Keep active strategy documents
free of executable commands for retired helpers; historical commands belong in
`docs/archive/experiments_ai_crm_next/`.
