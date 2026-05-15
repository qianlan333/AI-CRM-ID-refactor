from __future__ import annotations

import json
import os
import urllib.request

from scripts import internal_http


DEFAULT_PATH = "/api/archive/sync"


def run() -> str:
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = os.getenv("APP_PORT", "5000")
    owner_userid = os.getenv("WECOM_DEFAULT_OWNER_USERID", "")
    payload = {
        "start_time": "2000-01-01 00:00:00",
        "end_time": "2099-12-31 23:59:59",
        "owner_userid": owner_userid,
        "cursor": "",
    }
    response_payload = internal_http.post_json(
        host=host,
        port=port,
        path=DEFAULT_PATH,
        payload=payload,
        timeout_seconds=120,
        urlopen=urllib.request.urlopen,
    )
    body = json.dumps(response_payload, ensure_ascii=False)
    print(body)
    return body


def main() -> None:
    run()


if __name__ == "__main__":
    main()
