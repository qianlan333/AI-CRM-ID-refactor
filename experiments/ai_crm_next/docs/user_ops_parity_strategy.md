# User Ops Parity Strategy

## Purpose

User Ops cannot be replaced safely until old Flask AI-CRM and AI-CRM Next return compatible API contracts for the copied legacy frontend. The parity layer records old response shapes, checks AI-CRM Next responses against the same contract, and produces repeatable JSON/Markdown reports before any production cutover.

This is a contract comparison mechanism, not a new User Ops feature.

## Modes

### HTTP Mode

Use this when old Flask and AI-CRM Next are both running:

```bash
python experiments/ai_crm_next/tools/compare_user_ops_parity.py \
  --old-base-url http://127.0.0.1:5001 \
  --next-base-url http://127.0.0.1:8000 \
  --output-md historical removed reference (user_ops_parity_report.md) \
  --output-json historical removed reference (user_ops_parity_report.json)
```

The tool only sends HTTP requests. It must not import the old Flask app or old backend packages.

### Fixture Mode

Use this when the old service is not running:

```bash
python experiments/ai_crm_next/tools/compare_user_ops_parity.py \
  --old-fixture-dir tests/fixtures/old_user_ops \
  --next-testclient \
  --output-md /tmp/user_ops_parity_report.md \
  --output-json /tmp/user_ops_parity_report.json
```

The fixtures under `tests/fixtures/old_user_ops/` are anonymized minimum-shape samples. They are not complete production exports and should be replaced with fresh sampled responses before a real cutover decision.

## Side-Effect Safety

By default the compare tool excludes write endpoints such as DND and batch-send execute. Safe default coverage includes:

- `GET /api/admin/user-ops/overview`
- `GET /api/admin/user-ops/list`
- `GET /api/admin/user-ops/list?wecom_status=added`
- `GET /api/admin/user-ops/list?wecom_status=not_added`
- `POST /api/admin/user-ops/batch-send/preview`
- `GET /api/admin/user-ops/send-records`

`POST /api/admin/user-ops/batch-send/execute` is only compared with `--include-write-endpoints`. AI-CRM Next still uses fake dispatch; do not run write comparison against production old Flask unless the old environment is explicitly isolated and safe.

## Allowed Differences

- `generated_at`
- `created_at`
- `updated_at`
- `id` values
- `record_id` values
- fixture row counts and dynamic count values
- additional backward-compatible fields

## Disallowed Differences

- missing required keys
- incompatible required-key type families
- missing overview card labels
- missing `skipped_by_reason` in preview
- execute not requiring `confirm=true`
- DND response shape changes
- send-record list/detail shape changes
- `/admin/user-ops/ui` raw HTML smoke regression

## Updating Fixtures

1. Run old Flask in a safe environment.
2. Sample only the User Ops endpoints listed above.
3. Redact customer names, mobiles, external user IDs, and operator IDs.
4. Save responses as `status_code` plus `payload`.
5. Run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python experiments/ai_crm_next/tools/compare_user_ops_parity.py \
  --old-fixture-dir tests/fixtures/old_user_ops \
  --next-testclient \
  --output-md /tmp/user_ops_parity_report.md \
  --output-json /tmp/user_ops_parity_report.json
```

## Current Status

User Ops remains `partial`. AI-CRM Next has PostgreSQL-ready repo tests and parity comparison tooling, but it has not replaced old User Ops, has not connected to production PostgreSQL, and does not call real WeCom.
