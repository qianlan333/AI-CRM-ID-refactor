# Phase 5U Media Upload Adapter Contract + Fake/Stub Runtime

## Status

- phase_5u_media_upload_adapter_contract_fake_stub
- contract + fake/stub runtime readiness
- no live provider upload
- no production media publish
- no public media URL publication
- no raw file exposure
- no file delete
- no route owner switch
- no fallback removal
- no production_compat change
- no outbound send
- delete_ready false

## Contract Scope

This bundle covers media upload / media library external adapter readiness for:

- `/api/admin/image-library*`
- `/api/admin/image-library/upload`
- `/api/admin/attachment-library*`
- `/api/admin/miniprogram-library*`

Contract shape:

- validate_media_metadata
- dry_run_upload_media
- dry_run_lookup_media
- dry_run_provider_reference
- dry_run_publish_reference_policy

The existing fake/stub adapter boundary under `aicrm_next.integration_gateway.media_adapters` remains the runtime reference. This bundle adds Phase 5U evidence runners, machine-readable policy, checker, tests, and phase state handoff. It does not add live provider upload code.

## Fake/Stub Behavior

- deterministic fake media metadata
- deterministic fake storage key / media id evidence
- no network call
- no provider token usage
- no provider secret usage
- no raw file dump
- no public URL publication by default
- no destructive delete
- no production owner switch
- no production_compat change

## File Metadata Policy

- Allowed MIME types: `image/png`, `image/jpeg`, `image/webp`, `application/pdf`
- Allowed extensions: `.png`, `.jpg`, `.jpeg`, `.webp`, `.pdf`
- Max dry-run size: 5 MiB
- Raw file bytes must not be printed.
- Public URLs and provider references must be redacted in evidence.

## Idempotency / Replay Policy

- Idempotency key is required for future write-like media uploads.
- Same key and same metadata returns deterministic replay evidence.
- Same key and different metadata must be treated as conflict in future live bundles.
- Retry is safe because Phase 5U enables no external side effect.

## Evidence Policy

Evidence must include:

- adapter_mode
- route_family
- idempotency_key
- request_hash
- metadata validation result
- public URL redaction marker
- raw file exposure marker
- live_provider_upload_executed=false
- public_media_url_published=false
- destructive_delete_executed=false
- side_effect_safety
- timestamp

## Readiness Packages

- staging fake/stub smoke runner: `tools/run_phase5u_media_upload_fake_stub_staging_smoke.py`
- production fake/stub dry-run runner: `tools/run_phase5u_media_upload_fake_stub_production_dry_run.py`

## Phase 5V Recommendation

Next bundle:

- `phase_5v_media_upload_live_adapter_behind_flag_bundle`
- route family: `/api/admin/image-library*`

Phase 5V may add live adapter code behind explicit flags, but live upload must remain disabled by default and public publication / destructive delete must remain separately gated.
