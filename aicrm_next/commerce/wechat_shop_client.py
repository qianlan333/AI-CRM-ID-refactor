from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


class WeChatShopClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = dict(payload or {})


@dataclass(frozen=True)
class WeChatShopClientConfig:
    appid: str
    appsecret: str
    api_base: str = "https://api.weixin.qq.com"
    timeout_seconds: int = 5


def _text(value: Any) -> str:
    return str(value or "").strip()


class WeChatShopClient:
    """Narrow WeChat Shop API client for order read/sync only."""

    def __init__(self, config: WeChatShopClientConfig) -> None:
        self.config = config

    def _post_json(self, api_path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.config.api_base.rstrip('/')}{api_path}"
        try:
            response = requests.post(
                url,
                json=payload,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=max(1, int(self.config.timeout_seconds or 5)),
            )
        except requests.RequestException as exc:
            raise WeChatShopClientError(f"wechat_shop request failed: {exc}") from exc
        try:
            data = response.json() if response.text else {}
        except ValueError:
            data = {"raw": response.text}
        errcode = data.get("errcode")
        if response.status_code >= 300 or errcode not in {None, 0, "0"}:
            message = str(data.get("errmsg") or data.get("errcode") or response.text or "wechat_shop_http_error")
            raise WeChatShopClientError(message, status_code=response.status_code, payload=data)
        return data

    def get_stable_access_token(self, force_refresh: bool = False) -> dict[str, Any]:
        if not _text(self.config.appid) or not _text(self.config.appsecret):
            raise WeChatShopClientError("WECHAT_SHOP_APPID and WECHAT_SHOP_APPSECRET are required")
        return self._post_json(
            "/cgi-bin/stable_token",
            {
                "grant_type": "client_credential",
                "appid": self.config.appid,
                "secret": self.config.appsecret,
                "force_refresh": bool(force_refresh),
            },
        )

    def get_order(self, order_id: str, access_token: str) -> dict[str, Any]:
        token = _text(access_token)
        normalized_order_id = _text(order_id)
        if not normalized_order_id:
            raise WeChatShopClientError("order_id is required")
        if not token:
            raise WeChatShopClientError("access_token is required")
        return self._post_json(
            f"/channels/ec/order/get?access_token={token}",
            {"order_id": normalized_order_id},
        )

    def gen_after_sale_order(self, payload: dict[str, Any], access_token: str) -> dict[str, Any]:
        token = _text(access_token)
        if not token:
            raise WeChatShopClientError("access_token is required")
        return self._post_json(
            f"/channels/ec/aftersale/genaftersaleorder?access_token={token}",
            dict(payload or {}),
        )
