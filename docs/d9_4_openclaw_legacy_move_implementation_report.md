# D9.4 OpenClaw Legacy Move Implementation Report

## Scope

D9.4 moves the frozen OpenClaw legacy marker into `legacy_flask/openclaw_legacy/` and keeps `openclaw_service/` as a compatibility shim. The current source tree had no OpenClaw business implementation files beyond the frozen marker, so the move is metadata-only.

## Moved Files

- `legacy_flask/openclaw_legacy/LEGACY_FROZEN.md`
- `legacy_flask/openclaw_legacy/README.md`
- `legacy_flask/openclaw_legacy/MOVE_PENDING.md`
- `legacy_flask/openclaw_legacy/__init__.py`

## Remaining Shim Files

- `openclaw_service/__init__.py`
- `openclaw_service/README.md`
- `openclaw_service/LEGACY_FROZEN.md`

## Import Rewrite Summary

Old `import openclaw_service` callers continue to import the compatibility shim. The shim forwards only metadata from `legacy_flask.openclaw_legacy` and does not expose a runtime OpenClaw adapter.

AI-CRM Next runtime code continues to use the D7.7 MCP/OpenClaw adapter boundary in `aicrm_next/integration_gateway`.

## Compatibility Behavior

The shim contains `LEGACY_COMPATIBILITY_SHIM = True` and points to `legacy_flask.openclaw_legacy`. It is retained for rollback/reference compatibility only.

## Safety Status

- no production config change
- no production traffic cutover
- no real OpenClaw call
- no real MCP external call
- no webhook delivery
- no old system write endpoint execution
- no production approval marker
- no production ownership marker
- no deletion approval marker

## Rollback

D9.4 can be reverted by removing the shim files and restoring the D9.3 skeleton text. Because no production config or runtime traffic path changed, rollback is file-only.

## Next Step

D9.5 adds shim-removal planning only. The shim remains retained until observation evidence, final reference scan evidence, rollback proof, and human signoff are available.
