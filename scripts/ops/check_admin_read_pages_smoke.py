from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REQUIRED_OPENAPI_PATHS = (
    "/api/admin/push-center/stats",
    "/api/admin/push-center/jobs",
    "/api/admin/internal-events",
    "/api/admin/wecom/tags",
    "/api/admin/wecom/tag-groups",
    "/api/admin/automation-conversion/group-ops/plans",
    "/api/admin/automation-conversion/group-ops/groups",
    "/api/admin/ai-audience/packages",
    "/api/admin/automation-agents",
    "/api/admin/user-ops/send-records",
    "/api/admin/data-health/summary",
    "/api/admin/data-health/checks",
    "/api/admin/delivery-lineage",
    "/api/admin/growth-orchestration/programs",
)

SMOKE_PATHS = (
    "/admin/customers",
    "/admin/automation-conversion",
    "/admin/automation-conversion/group-ops/ui",
    "/admin/wecom-tags",
    "/admin/push-center",
    "/admin/internal-events",
    "/admin/automation-agents",
    "/api/admin/push-center/stats",
    "/api/admin/push-center/jobs?limit=1",
    "/api/admin/internal-events?limit=1",
    "/api/admin/wecom/tags",
    "/api/admin/wecom/tag-groups",
    "/api/admin/automation-conversion/group-ops/plans?limit=1",
    "/api/admin/automation-conversion/group-ops/groups?limit=1",
    "/api/admin/ai-audience/packages",
    "/api/admin/automation-agents",
    "/api/admin/user-ops/send-records?limit=1",
    "/api/admin/data-health/summary",
)


@dataclass(frozen=True)
class ProbeResult:
    path: str
    status_code: int
    ok: bool
    duration_ms: int
    error: str = ""
    body_prefix: str = ""


def _admin_cookie_header() -> str:
    try:
        from aicrm_next.admin_auth.service import SESSION_COOKIE, sign_session
    except Exception:
        return ""
    payload = {
        "auth_source": "deploy_smoke",
        "login_type": "deploy_smoke",
        "username": "deploy-smoke",
        "display_name": "deploy-smoke",
        "roles": ["super_admin"],
        "iat": int(time.time()),
    }
    try:
        return f"{SESSION_COOKIE}={sign_session(payload)}"
    except Exception:
        return ""


def _fetch(
    base_url: str,
    path: str,
    *,
    timeout: float,
    max_bytes: int = 4096,
    cookie_header: str = "",
) -> tuple[int, dict[str, str], str]:
    url = f"{base_url.rstrip('/')}{path}"
    headers = {"User-Agent": "aicrm-admin-read-smoke/1"}
    if cookie_header:
        headers["Cookie"] = cookie_header
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw_body = response.read(max_bytes) if max_bytes > 0 else response.read()
            body = raw_body.decode("utf-8", "replace")
            return int(response.status), dict(response.headers.items()), body
    except HTTPError as exc:
        raw_body = exc.read(max_bytes) if max_bytes > 0 else exc.read()
        body = raw_body.decode("utf-8", "replace")
        return int(exc.code), dict(exc.headers.items()), body


def _probe(base_url: str, path: str, *, timeout: float, cookie_header: str = "") -> ProbeResult:
    started = time.monotonic()
    try:
        status_code, _headers, body = _fetch(base_url, path, timeout=timeout, cookie_header=cookie_header)
    except (URLError, TimeoutError, OSError) as exc:
        return ProbeResult(
            path=path,
            status_code=0,
            ok=False,
            duration_ms=int((time.monotonic() - started) * 1000),
            error=exc.__class__.__name__,
        )
    ok = status_code < 500
    return ProbeResult(
        path=path,
        status_code=status_code,
        ok=ok,
        duration_ms=int((time.monotonic() - started) * 1000),
        body_prefix=body[:180].replace("\n", " "),
    )


def _openapi_paths(base_url: str, *, timeout: float, cookie_header: str = "") -> set[str]:
    status_code, _headers, body = _fetch(base_url, "/openapi.json", timeout=timeout, max_bytes=0, cookie_header=cookie_header)
    if status_code >= 500:
        raise RuntimeError(f"openapi returned {status_code}")
    payload = json.loads(body)
    paths = payload.get("paths")
    if not isinstance(paths, dict):
        raise RuntimeError("openapi paths is not an object")
    return set(paths)


def run(base_url: str, *, timeout: float) -> dict[str, Any]:
    cookie_header = _admin_cookie_header()
    paths = _openapi_paths(base_url, timeout=timeout, cookie_header=cookie_header)
    missing_paths = [path for path in REQUIRED_OPENAPI_PATHS if path not in paths]
    probes = [_probe(base_url, path, timeout=timeout, cookie_header=cookie_header) for path in SMOKE_PATHS]
    failed_probes = [probe for probe in probes if not probe.ok]
    return {
        "ok": not missing_paths and not failed_probes,
        "admin_cookie_supplied": bool(cookie_header),
        "base_url": base_url.rstrip("/"),
        "openapi_path_count": len(paths),
        "missing_openapi_paths": missing_paths,
        "probes": [probe.__dict__ for probe in probes],
        "failed_paths": [probe.path for probe in failed_probes],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke test production admin read pages and APIs.")
    parser.add_argument("--base-url", default="http://127.0.0.1:5001")
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args(argv)
    payload = run(args.base_url, timeout=max(1.0, float(args.timeout)))
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
