# Questionnaire H5 / OAuth Readiness Runbook

This runbook collects readonly evidence for AI-CRM Next questionnaire H5 and
WeChat OAuth guardrails. It does not enable real OAuth, timers, production
cutover, or legacy fallback removal.

## Business Impact

Questionnaire H5 is the signup and conversion path for users who open a public
questionnaire, pass through guarded OAuth, submit answers, and view a result.
This evidence pack helps detect 404/500 responses, localhost redirects,
fixture/demo data leaks, and ambiguous OAuth mode before the route is treated
as production-ready.

## Scope

Readonly probes cover:

- `/admin/questionnaires`
- `/api/admin/questionnaires`
- `/api/h5/questionnaires/{slug}`
- `/s/{slug}`
- `/api/h5/wechat/oauth/start`
- `/api/h5/wechat/oauth/callback`
- `/api/h5/questionnaires/{slug}/result/{submission_id}`

The checker separates:

- `local_checker_evidence`: local TestClient shape and guardrail checks.
- `server_readonly_evidence`: optional readonly GET probes against a running
  server.
- `production_canary_evidence`: always false for this checker.

## Local Command

```bash
.venv/bin/python tools/check_questionnaire_h5_oauth_readiness.py \
  --output-md /tmp/questionnaire_h5_oauth_readiness.md \
  --output-json /tmp/questionnaire_h5_oauth_readiness.json
```

Local production probes intentionally use a loopback PostgreSQL URL so missing
server data is reported as local probe warnings, not as production canary
approval.

## Server Readonly Command

Run from the server checkout when collecting readonly evidence:

```bash
cd /home/ubuntu/极简 crm
source /home/ubuntu/.openclaw-wecom-pg.env
source /home/ubuntu/venvs/openclaw/bin/activate
python3 tools/check_questionnaire_h5_oauth_readiness.py \
  --base-url http://127.0.0.1:5001 \
  --output-md /tmp/questionnaire_h5_oauth_readiness.md \
  --output-json /tmp/questionnaire_h5_oauth_readiness.json
```

This command performs GET requests only. It must not be paired with any POST
submit, write, timer, or OAuth provider callback command.

## Pass Criteria

- Routes are not 404.
- OAuth start and callback return an explicit guarded `source_status`, such as
  `fake`, `staging_fake`, `missing_config`, or `adapter_error`.
- OAuth responses do not contain localhost or loopback redirect targets in
  production/server evidence.
- Production-ready probes do not return `hxc-activation-v1`, `disabled-demo`,
  fixture, local_contract, or demo content as a successful production payload.
- Questionnaire list payloads retain `items` or `questionnaires` shape.
- Public questionnaire payloads retain `questionnaire` and `questions` shape.
- Result payloads retain `result` and `result_message` shape.

## Safety / Non-Goals

- Do not enable `AICRM_NEXT_ENABLE_REAL_WECHAT_OAUTH`.
- Do not call a real WeChat OAuth endpoint.
- Do not submit questionnaire answers.
- Do not modify nginx, systemd, deploy files, or timers.
- Do not treat this output as production cutover approval or production canary
  evidence.

## Rollback

This PR adds only docs, tests, and a checker. Rollback is reverting the checker,
test, and runbook files; no runtime behavior or production configuration is
changed.
