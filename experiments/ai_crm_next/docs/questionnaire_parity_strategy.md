# Questionnaire Parity Strategy

## Purpose

Questionnaire migration starts by locking contract parity before replacing the old Flask implementation. The old admin questionnaire UI and public H5 experience remain the product baseline.

## Scope

First-slice parity covers:

- admin questionnaire list/detail/preflight;
- create/update/enable/disable/delete/export/debug contract stubs;
- public H5 questionnaire read;
- fixture-safe submit pipeline;
- result readback;
- fake WeChat OAuth start/callback;
- identity-resolution boundary through `identity_contact`.

## Modes

Fixture mode:

```bash
python retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md \
  --old-fixture-dir tests/fixtures/old_questionnaire \
  --next-testclient \
  --output-md /tmp/questionnaire_parity_report.md \
  --output-json /tmp/questionnaire_parity_report.json
```

HTTP mode is reserved for isolated dual-run environments:

```bash
python retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md \
  --old-base-url http://127.0.0.1:5001 \
  --next-base-url http://127.0.0.1:8000 \
  --output-md /tmp/questionnaire_parity_report.md \
  --output-json /tmp/questionnaire_parity_report.json
```

Do not point HTTP mode at old production submit endpoints. Submit comparison must use fixtures or an isolated fake dataset.

## Allowed Differences

- ids, timestamps, and submission ids may differ;
- fixture counts may differ;
- redirect host may differ;
- fake OAuth values may differ.

## Disallowed Differences

- missing required top-level keys;
- missing questionnaire/question/option fields;
- missing preflight checks;
- missing submit fields such as `submission_id`, `score`, `final_tags`, `person_id`, or `redirect_url`;
- real WeChat OAuth exchange;
- real WeCom tagging/contact call;
- real external webhook push;
- UI redesign or new questionnaire frontend replacement.

## Current Status

Status is `partial`.

The first slice is fixture-backed. It does not connect to production PostgreSQL, does not call real WeChat OAuth, does not call WeCom, does not send external webhooks, and does not replace the old questionnaire system.
