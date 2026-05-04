from __future__ import annotations

import json
import os
import sys
import urllib.request
import uuid


def main() -> None:
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = os.getenv("APP_PORT", "5000")
    owner_userid = os.getenv("WECOM_DEFAULT_OWNER_USERID", "")
    payload = {
        "start_time": "2000-01-01 00:00:00",
        "end_time": "2099-12-31 23:59:59",
        "owner_userid": owner_userid,
        "cursor": "",
    }
    request_id = "cron-archive-" + uuid.uuid4().hex[:16]
    request = urllib.request.Request(
        f"http://{host}:{port}/api/archive/sync",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Request-Id": request_id},
        method="POST",
    )
    print(f"[run_incremental_archive_sync] request_id={request_id}", file=sys.stderr)
    with urllib.request.urlopen(request, timeout=120) as response:
        print(response.read().decode("utf-8"))


if __name__ == "__main__":
    main()
