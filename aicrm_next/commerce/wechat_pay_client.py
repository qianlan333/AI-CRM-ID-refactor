from __future__ import annotations

import base64
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class WeChatPayClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = dict(payload or {})


@dataclass(frozen=True)
class WeChatPayClientConfig:
    app_id: str
    mch_id: str
    api_v3_key: str
    private_key_path: str
    merchant_serial_no: str
    platform_public_key_path: str = ""
    platform_serial_no: str = ""
    api_base: str = "https://api.mch.weixin.qq.com"
    timeout_seconds: int = 10


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    path = parsed.path or "/"
    return f"{path}?{parsed.query}" if parsed.query else path


def _json_body(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _load_private_key(path: str):
    if not _normalized_text(path):
        raise WeChatPayClientError("WECHAT_PAY_PRIVATE_KEY_PATH is required")
    try:
        key_bytes = Path(path).read_bytes()
        return serialization.load_pem_private_key(key_bytes, password=None)
    except Exception as exc:  # pragma: no cover - file/env defensive path
        raise WeChatPayClientError(f"failed to load WeChat Pay merchant private key: {exc}") from exc


class WeChatPayClient:
    """Narrow WeChat Pay API v3 client for Next-owned refund execution."""

    def __init__(self, config: WeChatPayClientConfig) -> None:
        self.config = config

    def _merchant_signature(self, message: str) -> str:
        private_key = _load_private_key(self.config.private_key_path)
        signature = private_key.sign(
            message.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("ascii")

    def _authorization_header(self, *, method: str, canonical_url: str, body: str) -> str:
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex
        message = f"{method.upper()}\n{canonical_url}\n{timestamp}\n{nonce}\n{body}\n"
        signature = self._merchant_signature(message)
        return (
            "WECHATPAY2-SHA256-RSA2048 "
            f'mchid="{self.config.mch_id}",'
            f'nonce_str="{nonce}",'
            f'timestamp="{timestamp}",'
            f'serial_no="{self.config.merchant_serial_no}",'
            f'signature="{signature}"'
        )

    def _request_json(self, method: str, api_path: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = _json_body(payload or {}) if method.upper() != "GET" else ""
        canonical = _canonical_url(api_path)
        url = f"{self.config.api_base.rstrip('/')}{canonical}"
        headers = {
            "Accept": "application/json",
            "Authorization": self._authorization_header(method=method, canonical_url=canonical, body=body),
            "Content-Type": "application/json",
        }
        platform_serial_no = _normalized_text(self.config.platform_serial_no)
        if platform_serial_no.startswith("PUB_KEY_ID_"):
            headers["Wechatpay-Serial"] = platform_serial_no
        try:
            response = requests.request(
                method,
                url,
                data=body.encode("utf-8"),
                headers=headers,
                timeout=max(1, int(self.config.timeout_seconds or 10)),
            )
        except requests.RequestException as exc:
            raise WeChatPayClientError(f"wechat_pay request failed: {exc}") from exc
        try:
            response_payload = response.json() if response.text else {}
        except ValueError:
            response_payload = {"raw": response.text}
        if response.status_code >= 300:
            message = str(
                response_payload.get("message")
                or response_payload.get("code")
                or response.text
                or "wechat_pay_http_error"
            )
            raise WeChatPayClientError(message, status_code=response.status_code, payload=response_payload)
        return response_payload

    def create_refund(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json("POST", "/v3/refund/domestic/refunds", payload=payload)
