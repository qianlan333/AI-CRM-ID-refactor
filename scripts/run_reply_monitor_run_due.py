from __future__ import annotations

import argparse
import os
import urllib.request

from scripts import internal_http
from scripts.script_runtime import emit_json, read_app_host, read_app_port, read_int_env, read_internal_api_token


DEFAULT_OPERATOR = "reply_monitor_run_due_timer"
DEFAULT_PATH = "/api/admin/automation-conversion/reply-monitor/run-due"
DEFAULT_LIMIT = 20
DEFAULT_RETRY_COUNT = 6
DEFAULT_RETRY_INTERVAL_SECONDS = 10


def run(*, limit: int = DEFAULT_LIMIT, dry_run: bool = True) -> str:
    host = read_app_host()
    port = read_app_port()
    token = read_internal_api_token()
    operator = os.getenv("REPLY_MONITOR_RUN_DUE_OPERATOR", DEFAULT_OPERATOR).strip() or DEFAULT_OPERATOR
    path = os.getenv("REPLY_MONITOR_RUN_DUE_PATH", DEFAULT_PATH).strip() or DEFAULT_PATH
    retry_count = read_int_env("REPLY_MONITOR_RUN_DUE_RETRY_COUNT", DEFAULT_RETRY_COUNT)
    retry_interval_seconds = read_int_env("REPLY_MONITOR_RUN_DUE_RETRY_INTERVAL_SECONDS", DEFAULT_RETRY_INTERVAL_SECONDS)
    if not token:
        return emit_json(
            {
                "ok": False,
                "status": "skipped",
                "error_code": "automation_internal_token_not_configured",
                "source_status": "next_reply_monitor_run_due_timer_config",
                "route_owner": "ai_crm_next",
                "fallback_used": False,
                "real_external_call_executed": False,
                "automation_runtime_executed": False,
                "wecom_send_executed": False,
                "reply_monitor_run_due_executed": False,
                "message": "AUTOMATION_INTERNAL_API_TOKEN is required before the reply monitor timer can call the Next route.",
            }
        )
    payload = internal_http.post_json(
        host=host,
        port=port,
        token=token,
        path=path,
        payload={"operator": operator, "limit": limit, "dry_run": dry_run},
        retry_count=retry_count,
        retry_interval_seconds=retry_interval_seconds,
        urlopen=urllib.request.urlopen,
    )
    return emit_json(payload)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Next-native reply monitor due timer contract.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", dest="dry_run", action="store_false")
    return parser


def main() -> None:
    args = _parser().parse_args()
    run(limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
