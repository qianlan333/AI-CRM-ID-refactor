# Phase 5AK Questionnaire External Submit Contract + Fake/Stub

## Status

- phase_5ak_questionnaire_external_submit_contract_fake_stub
- contract and fake/stub readiness only
- no production public submit owner switch
- no production identity write
- no production tag write
- no live OAuth callback cutover
- no outbound send
- no batch tag write
- no production_compat change
- no fallback removal
- delete_ready false

## Contract scope

This bundle covers questionnaire public/external submit and tag writeback edge contracts for `/api/h5/questionnaires*`, `/api/h5/questionnaires/{slug}/submit`, and `/s/{slug}`. It defines dry-run public submit evidence, dry-run identity mapping evidence, dry-run tag writeback evidence, validation, idempotency, duplicate submission policy, and redaction rules.

## Fake/stub behavior

The fake/stub adapter returns deterministic fake questionnaire submission metadata. It does not write production submit data, identity mappings, or tags. It does not call OAuth, WeCom, OpenClaw/MCP, payment, media, outbound send, timers, or automation. `external_userid`, `openid`, `unionid`, and mobile are redacted in evidence.

## Idempotency and duplicate policy

Dry-run write-like operations require an idempotency key. Same key and same request hash returns replay evidence. Same key and different request hash returns conflict. Missing keys return `idempotency_key_required`.

## Evidence policy

Evidence includes adapter mode, result status, slug, answer keys, redacted identity fields, idempotency key, request hash, side-effect safety, and timestamp. Fixture or fake/stub evidence must not be claimed as production submit or production tag write success.

## Next bundle

Next: phase_5al_questionnaire_external_submit_live_adapter_behind_flag_bundle.

The next bundle may introduce live adapter code behind explicit flags only. It must not switch public submit ownership, write production identity/tag by default, remove fallback, or change production_compat.
