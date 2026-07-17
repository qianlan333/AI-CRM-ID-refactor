#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

try:
    from scripts.script_runtime import ensure_repo_root_on_path, print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()

from aicrm_next.customer_read_model.refresh_intents import CustomerReadModelRefreshIntentService  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a customer read-model refresh intent; never rebuild inline.")
    parser.add_argument("--execute", action="store_true", default=False, help="Deprecated compatibility flag; still writes intent only.")
    parser.add_argument("--max-customers", type=int, default=None, help="Deprecated; retained for CLI compatibility and ignored.")
    parser.add_argument("--source-key", default="")
    args = parser.parse_args(argv)
    try:
        now = datetime.now(timezone.utc)
        bucket = now.strftime("%Y-%m-%dT%H:%M")
        result = CustomerReadModelRefreshIntentService().request_refresh(
            source_event_key=str(args.source_key or f"compatibility_clock:{bucket}").strip(),
            source_event_type="customer_read_model.compatibility_clock",
        )
    except Exception as exc:
        message = str(exc)
        reason = (
            message
            if isinstance(exc, RuntimeError) and message.startswith("customer_read_model_")
            else "customer_read_model_refresh_failed"
        )
        print_json({"ok": False, "error": type(exc).__name__, "reason": reason})
        return 1
    print_json({"accepted": bool(result.get("ok")), **result, "inline_refresh_executed": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
