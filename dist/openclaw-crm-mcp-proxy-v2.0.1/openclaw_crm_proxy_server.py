#!/usr/bin/env python3
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
from flask import Flask, Response, jsonify, request


DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_RETRY_COUNT = 0


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return max(0, int(raw))


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _health_url_for(mcp_url: str) -> str | None:
    parts = urlsplit(mcp_url)
    if not parts.scheme or not parts.netloc:
        return None
    path = parts.path or ""
    if path.endswith("/mcp"):
        path = path[: -len("/mcp")] + "/health"
    else:
        path = path.rstrip("/") + "/health"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def create_app() -> Flask:
    app = Flask(__name__)

    session = requests.Session()
    retry_count = _env_int("CRM_MCP_RETRY_COUNT", DEFAULT_RETRY_COUNT)
    timeout_seconds = _env_int("CRM_MCP_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)

    def remote_mcp_url() -> str:
        return _required_env("CRM_MCP_URL")

    def bearer_token() -> str:
        return _required_env("MCP_BEARER_TOKEN")

    def forward_mcp(payload: Any) -> requests.Response:
        last_error: Exception | None = None
        headers = {
            "Authorization": f"Bearer {bearer_token()}",
            "Content-Type": "application/json",
        }
        for _ in range(retry_count + 1):
            try:
                return session.post(
                    remote_mcp_url(),
                    json=payload,
                    headers=headers,
                    timeout=timeout_seconds,
                )
            except requests.Timeout as exc:
                last_error = exc
            except requests.ConnectionError as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    @app.get("/health")
    def health() -> Response:
        remote_url = os.getenv("CRM_MCP_URL", "").strip()
        payload: dict[str, Any] = {
            "ok": True,
            "service": "openclaw-crm-mcp-proxy",
            "mode": "thin-proxy",
            "remote_configured": bool(remote_url),
        }
        if remote_url:
            health_url = _health_url_for(remote_url)
            if health_url:
                try:
                    upstream = session.get(health_url, timeout=min(timeout_seconds, 5))
                    payload["remote_health"] = {
                        "reachable": upstream.ok,
                        "status_code": upstream.status_code,
                    }
                except requests.RequestException as exc:
                    payload["remote_health"] = {
                        "reachable": False,
                        "error": exc.__class__.__name__,
                    }
        return jsonify(payload)

    @app.post("/mcp")
    def mcp() -> Response:
        try:
            payload = request.get_json(force=True, silent=False)
        except Exception as exc:  # pragma: no cover
            return jsonify(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Invalid JSON payload: {exc}"},
                }
            ), 400

        try:
            upstream = forward_mcp(payload)
        except RuntimeError as exc:
            return jsonify(
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id") if isinstance(payload, dict) else None,
                    "error": {"code": -32001, "message": str(exc)},
                }
            ), 500
        except requests.Timeout:
            return jsonify(
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id") if isinstance(payload, dict) else None,
                    "error": {
                        "code": -32002,
                        "message": "CRM MCP upstream request timed out",
                    },
                }
            ), 504
        except requests.ConnectionError:
            return jsonify(
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id") if isinstance(payload, dict) else None,
                    "error": {
                        "code": -32003,
                        "message": "CRM MCP upstream is unreachable",
                    },
                }
            ), 502

        response_headers = {"Content-Type": upstream.headers.get("Content-Type", "application/json")}
        return Response(
            upstream.content,
            status=upstream.status_code,
            headers=response_headers,
        )

    return app


def main() -> None:
    app = create_app()
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = _env_int("APP_PORT", 5001)
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()
