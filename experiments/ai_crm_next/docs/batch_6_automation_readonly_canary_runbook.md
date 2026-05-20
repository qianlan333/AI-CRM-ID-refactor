# Batch 6 Automation Readonly Canary Runbook

This runbook is for staging or production-like canary preparation/execution. It is not a production cutover instruction.

## Pre-Check

1. Confirm worktree state.
   ```bash
   git status --short --untracked-files=all
   ```
2. Run ordinary pytest.
   ```bash
   .venv/bin/python -m pytest -q
   ```
3. Run six parity tools.
4. Run Automation parity.
   ```bash
   .venv/bin/python tools/compare_automation_conversion_parity.py \
     --old-fixture-dir tests/fixtures/old_automation_conversion \
     --next-testclient \
     --output-md /tmp/automation_parity_batch_6.md \
     --output-json /tmp/automation_parity_batch_6.json
   ```
5. Run Automation readonly gray smoke.
   ```bash
   .venv/bin/python tools/automation_readonly_gray_smoke.py \
     --old-base-url http://127.0.0.1:5001 \
     --next-testclient \
     --output-md /tmp/automation_readonly_gray_smoke_batch_6.md \
     --output-json /tmp/automation_readonly_gray_smoke_batch_6.json
   ```
6. Confirm screenshot baseline includes `/admin/automation-conversion`.
7. Confirm real PostgreSQL integration evidence exists.
8. Confirm route flags dry-run:
   - `AICRM_NEXT_ROUTE_AUTOMATION_READONLY=true`
   - `AICRM_NEXT_ROUTE_AUTOMATION_WRITES=false`
   - `AICRM_NEXT_AUTOMATION_ACTIVATION_WEBHOOK=false`
   - `AICRM_NEXT_AUTOMATION_WORKFLOW_RUNTIME=false`
   - `AICRM_NEXT_AUTOMATION_AGENT_RUNTIME=false`
   - `AICRM_NEXT_EXTERNAL_OPENCLAW=false`
   - `AICRM_NEXT_EXTERNAL_WECOM_DISPATCH=false`
   - `AICRM_NEXT_EXTERNAL_WEBHOOK=false`
9. Confirm accepted legacy route drift is documented:
   - old exact Next-style readonly route names may return 404
   - old aliases provide GET-only evidence with legacy payload shape
   - old admin page may return unauthenticated `302`

## Execute

1. Choose canary mode: `staging_simulated`, `staging_proxy`, `header_allowlist`, or `cookie_allowlist`.
2. Set dry-run or staging-only route flags.
3. Start old Flask staging if GET comparison is needed.
4. Start AI-CRM Next staging, or use TestClient for local simulated canary.
5. Optionally start staging proxy/router. Do not use production Nginx.
6. Run Automation readonly smoke through the canary target.
7. Run dual mode if old Flask is available.
8. Run screenshot route check.
9. Generate gray release report.
10. Generate readiness report.

## Monitor

- route status per included route
- 4xx / 5xx counts
- overview / pools / members / member detail / execution-records response shape
- old route alias and `legacy_missing_read_route` drift
- side-effect safety flags
- activation webhook flag
- OpenClaw flag
- WeCom dispatch flag
- external webhook flag
- workflow runtime flag
- agent runtime flag

## Rollback

1. Disable Automation readonly route flag.
   ```bash
   # PSEUDO ONLY - staging example
   AICRM_NEXT_ROUTE_AUTOMATION_READONLY=false
   ```
2. Route owner returns to old Flask.
3. Re-run old route smoke if old Flask is available.
4. Record rollback result and reason.
5. Preserve generated reports.

## Signoff

Record:

- operator
- evidence links
- canary mode
- database target
- external adapters mode
- smoke result
- parity result
- accepted legacy route drift
- rollback owner
- Go/No-Go decision
- production approval status

## Forbidden Actions

- Do not modify production Nginx or deploy configuration.
- Do not enable Automation write routes.
- Do not execute manual override.
- Do not execute confirm conversion.
- Do not execute enter-silent or exit-marketing.
- Do not execute activation webhook.
- Do not execute OpenClaw push.
- Do not execute workflow runtime or agent runtime.
- Do not execute real WeCom dispatch.
- Do not send external webhooks.
- Do not execute old Flask write endpoints.
- Do not represent staging-simulated evidence as production approval.
