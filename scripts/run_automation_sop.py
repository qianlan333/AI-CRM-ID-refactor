from __future__ import annotations

import json
import os
import urllib.request

from scripts import internal_http
from scripts.script_runtime import read_int_env


DEFAULT_OPERATOR = "automation_sop_runner"
DEFAULT_PATH = "/api/admin/automation-conversion/sop/run-due"
DEFAULT_RETRY_COUNT = 6
DEFAULT_RETRY_INTERVAL_SECONDS = 10


def build_request(*, host: str, port: str, token: str, operator: str, path: str = DEFAULT_PATH) -> urllib.request.Request:
    return internal_http.build_json_post_request(
        host=host,
        port=port,
        token=token,
        path=path,
        payload={"operator": operator, "jobs": ["sop"]},
    )


def run() -> str:
    host = os.getenv("APP_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = os.getenv("APP_PORT", "5000").strip() or "5000"
    token = os.getenv("AUTOMATION_INTERNAL_API_TOKEN", "").strip()
    operator = os.getenv("AUTOMATION_SOP_OPERATOR", DEFAULT_OPERATOR).strip() or DEFAULT_OPERATOR
    path = os.getenv("AUTOMATION_SOP_RUNNER_PATH", DEFAULT_PATH).strip() or DEFAULT_PATH
    retry_count = read_int_env("AUTOMATION_SOP_RETRY_COUNT", DEFAULT_RETRY_COUNT)
    retry_interval_seconds = read_int_env(
        "AUTOMATION_SOP_RETRY_INTERVAL_SECONDS",
        DEFAULT_RETRY_INTERVAL_SECONDS,
    )
    payload = internal_http.post_json(
        host=host,
        port=port,
        token=token,
        path=path,
        payload={"operator": operator, "jobs": ["sop"]},
        retry_count=retry_count,
        retry_interval_seconds=retry_interval_seconds,
        urlopen=urllib.request.urlopen,
    )
    body = json.dumps(payload, ensure_ascii=False)
    print(body)
    return body


def main() -> None:
    run()


if __name__ == "__main__":
    main()
