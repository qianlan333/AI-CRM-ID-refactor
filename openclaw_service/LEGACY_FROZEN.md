# Legacy Frozen: openclaw_service

`openclaw_service/` is now a legacy adapter/reference surface.

## Runtime Status

- Default AI-CRM runtime entry has moved to AI-CRM Next.
- OpenClaw-related legacy code remains only for fallback, comparison, and adapter reference.

## Allowed Changes

- Emergency rollback fixes.
- Migration reference work.
- Security or compatibility fixes needed to keep legacy fallback safe.

## Disallowed Changes

- New business features.
- New default runtime coupling.
- Real external adapter enablement without separate approval.

New replacement work must land in `aicrm_next/`. Deletion requires the legacy delete batch process.
