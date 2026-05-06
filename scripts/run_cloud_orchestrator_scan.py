"""定时扫描脚本 — 让 Cloud 编排端"自己醒过来"。

cron 每天 N 点跑一次：触发后端 ``/api/admin/cloud-orchestrator/scheduled-scan``，
该端点会启动一个无人值守的 Cloud Agent 会话（prompt 类似"扫描近 14 天沉默的
活跃-重点用户，按互动历史归类，对每类提出激活方案草稿"），生成的所有 plan
均处于 ``draft`` / ``simulated`` 状态，等待运营在 UI 审阅 + 确认。

环境变量：
- ``APP_HOST`` / ``APP_PORT`` — 后端 host/port
- ``AUTOMATION_INTERNAL_API_TOKEN`` — Bearer token（可选）
- ``CLOUD_ORCH_SCAN_OPERATOR`` — 运营标识（默认 cloud_scheduler）
- ``CLOUD_ORCH_SCAN_PROMPT`` — 自定义 prompt（缺省走默认沉默激活）
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request


DEFAULT_OPERATOR = "cloud_scheduler"
DEFAULT_PATH = "/api/admin/cloud-orchestrator/sessions"
DEFAULT_RETRY_COUNT = 3
DEFAULT_RETRY_INTERVAL_SECONDS = 15
DEFAULT_PROMPT = (
    "扫描近 14 天没有任何回复但近 60 天有过触达的活跃-重点（active_focus）"
    "和不活跃-重点（inactive_focus）池用户，按 profile_segment_key 分组归纳，"
    "对每组提出一份激活方案 draft：使用 draft_broadcast_plan 工具创建草稿，"
    "scenario_code 用 silent_wake，等运营审核后再发。"
    "完成后返回总览：总沉默人数、按 segment 的草稿 plan_id 列表。"
)


def build_request(
    *, host: str, port: str, token: str, operator: str, prompt: str, path: str = DEFAULT_PATH
) -> urllib.request.Request:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {
        "intent": prompt,
        "operator": operator,
        "trace_id": "",
        "session_id": "",
    }
    return urllib.request.Request(
        f"http://{host}:{port}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )


def run() -> str:
    host = os.getenv("APP_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = os.getenv("APP_PORT", "5000").strip() or "5000"
    token = os.getenv("AUTOMATION_INTERNAL_API_TOKEN", "").strip()
    operator = (os.getenv("CLOUD_ORCH_SCAN_OPERATOR") or DEFAULT_OPERATOR).strip() or DEFAULT_OPERATOR
    prompt = (os.getenv("CLOUD_ORCH_SCAN_PROMPT") or DEFAULT_PROMPT).strip()
    path = (os.getenv("CLOUD_ORCH_SCAN_PATH") or DEFAULT_PATH).strip() or DEFAULT_PATH
    retry_count = int((os.getenv("CLOUD_ORCH_SCAN_RETRY_COUNT") or DEFAULT_RETRY_COUNT))
    retry_interval_seconds = int(
        (os.getenv("CLOUD_ORCH_SCAN_RETRY_INTERVAL_SECONDS") or DEFAULT_RETRY_INTERVAL_SECONDS)
    )
    req = build_request(host=host, port=port, token=token, operator=operator, prompt=prompt, path=path)
    last_error: Exception | None = None
    for attempt in range(1, max(1, retry_count) + 1):
        try:
            with urllib.request.urlopen(req, timeout=600) as response:
                # SSE 流：聚合 events 打印
                lines = []
                for raw in response:
                    line = raw.decode("utf-8", errors="replace")
                    lines.append(line.rstrip("\n"))
                body = "\n".join(lines)
            print(body)
            return body
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            print(body)
            raise
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt >= max(1, retry_count):
                raise
            time.sleep(max(0, retry_interval_seconds))
    assert last_error is not None
    raise last_error


def main() -> None:
    run()


if __name__ == "__main__":
    main()
