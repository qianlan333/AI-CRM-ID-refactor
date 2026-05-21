# Go / No-Go Checklist

## D6.5 Dead Legacy Cleanup

| check | status | evidence |
| --- | --- | --- |
| Dead legacy inventory exists | PASS | `docs/legacy_dead_code_inventory.md` |
| Cleanup report exists | PASS | `docs/legacy_d6_5_dead_cleanup_report.md` |
| D7 blocker matrix exists | PASS | `docs/d7_write_external_blocker_matrix.md` |
| Checker exists | PASS | `tools/check_legacy_dead_cleanup.py` |
| Checker tests exist | PASS | `tests/test_legacy_dead_cleanup.py` |
| Actual deletion happened | PASS | orphan attachment template and stale generated route inventory removed |
| Protected fallback kept | PASS | write/external/runtime blocker matrix and checker protected files |
| Production config modified | NO | no deploy, production, nginx, systemd, or supervisor config change |
| Real traffic cutover | NO | cleanup only |
| External service call | NO | no WeCom, OAuth, Payment, OpenClaw, or cloud call |
| Old write endpoint executed | NO | no write smoke executed |
| Next write endpoint executed | NO | readonly parity and tests only |

## Go / No-Go

D6.5 can proceed to acceptance only after checker, fallback smoke, pytest, and six parity checks pass. D7 remains blocked until replacement plans and production evidence exist.
