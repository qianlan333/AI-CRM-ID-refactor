# Claude Production Sandbox Extension

This document records the server-side forced-command additions expected by
`scripts/prod.sh`. The forced command remains allowlisted: do not add a generic
shell, arbitrary Python runner, or write-capable bridge here.

## P1 Group Ops Workspace Bridge Diagnostic

Add this case to the production `~/claude-debug.sh` dispatcher:

```bash
diagnose-p1-bridge)
  cd "/home/ubuntu/极简 crm" || exit 1
  exec .venv/bin/python scripts/diagnose_p1_group_ops_workspace_bridge_acceptance.py
  ;;
```

Contract:

- dry-run / read-only only
- no shell passthrough
- no arbitrary script argument
- no external effect execution
- no Push Center execution worker
- no WeCom / webhook / message send
- no production migration
- no token, secret, raw receiver, raw external_userid, phone, raw target list, raw message body, or raw callback body output

The diagnostic may report `SKIPPED_WRITE_VALIDATION_SAFE_MODE` or
`EXTERNAL_EFFECT_JOB_READ_SKIPPED_PERMISSION_LIMITED` when production credentials
intentionally prevent safe aggregate reads. Those statuses are observability
signals, not execution success claims.
