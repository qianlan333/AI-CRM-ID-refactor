# Automation Conversion Parity Strategy

## Purpose

Automation Conversion is moving into AI-CRM Next one contract slice at a time. The old Flask automation pages and API shapes remain the product baseline; the new backend must prove compatible envelopes before any replacement.

## Current Status

- Backend status: `partial`.
- State machine status: `partial`.
- Admin automation frontend status: `partial adapter`.
- OpenClaw push status: `fake/stubbed`.
- Persistence: fixture/in-memory only.
- Production database: not connected.
- Real WeCom: not called.
- Real OpenClaw: not called.
- External webhook delivery: not called.

## Compared Contracts

The first parity spec covers:

- `GET /api/admin/automation-conversion/overview`
- `GET /api/admin/automation-conversion/pools`
- `GET /api/admin/automation-conversion/members`
- `GET /api/admin/automation-conversion/members/{member_id}`
- `POST /api/customer-automation/activation-webhook` in fixture/fake mode only
- `GET /api/admin/automation-conversion/execution-records`

## State Machine Semantics

- Questionnaire result only performs the first split into `normal` or `priority`.
- Later questionnaire results are stored as history/execution events but must not change `questionnaire_followup_type`, `followup_type`, or `current_pool`.
- If `manual_followup_type` is present, manual override remains higher priority than questionnaire output.
- Activated members keep their normal/priority branch when later questionnaire submissions arrive.
- Reset/re-evaluate behavior is intentionally outside this phase.

## Fixture Mode

Use anonymized fixtures:

```bash
python tools/compare_automation_conversion_parity.py \
  --old-fixture-dir tests/fixtures/old_automation_conversion \
  --next-testclient \
  --output-md /tmp/automation_conversion_parity_report.md \
  --output-json /tmp/automation_conversion_parity_report.json
```

Fixtures use obvious mask values such as `mobile_masked_001`, `external_user_masked_001`, and `customer_masked_001`.

## HTTP Mode

HTTP mode is reserved for isolated old/new staging services:

```bash
python tools/compare_automation_conversion_parity.py \
  --old-base-url http://127.0.0.1:5001 \
  --next-base-url http://127.0.0.1:8000 \
  --old-fixture-dir tests/fixtures/old_automation_conversion \
  --output-md /tmp/automation_conversion_parity_report.md \
  --output-json /tmp/automation_conversion_parity_report.json
```

Do not run write endpoints against old production. Activation and override style paths must remain fixture/fake unless an explicitly isolated test environment is provided.

## Allowed Differences

- Dynamic ids, timestamps, and record counts may differ.
- Fixture row values may differ.
- Extra fields are allowed when required legacy fields are present and type-compatible.

## Forbidden Differences

- Missing required keys.
- Incompatible type families for required fields.
- Missing pool/member state fields.
- Activation webhook shape drift.
- Execution-record shape drift.
- Real WeCom, OpenClaw, or external webhook calls during parity comparison.

## Updating Fixtures

When sampling the old Flask service, store only anonymized responses under `tests/fixtures/old_automation_conversion/`. Replace any phone-like, external-user-like, or customer-name-like data with explicit mask values before committing.
