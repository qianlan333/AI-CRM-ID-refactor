from __future__ import annotations

import json
import os
import urllib.request

from scripts import internal_http


DEFAULT_PATH = "/api/admin/automation-conversion/message-activity-sync/run"


def run() -> str:
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = os.getenv("APP_PORT", "5000")
    token = os.getenv("AUTOMATION_INTERNAL_API_TOKEN", "").strip()
    payload = {
        "trigger_source": "scheduled",
        "operator": "cron_message_activity_sync",
    }
    response_payload = internal_http.post_json(
        host=host,
        port=port,
        token=token,
        path=DEFAULT_PATH,
        payload=payload,
        timeout_seconds=180,
        urlopen=urllib.request.urlopen,
    )
    body = json.dumps(response_payload, ensure_ascii=False)
    print(body)
    return body


def main() -> None:
    run()


if __name__ == "__main__":
    main()
