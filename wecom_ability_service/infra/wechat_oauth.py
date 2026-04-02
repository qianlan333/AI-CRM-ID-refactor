from __future__ import annotations

from typing import Any

import requests


class WeChatOAuthRequestError(RuntimeError):
    pass


def exchange_wechat_oauth_code(*, app_id: str, app_secret: str, code: str, timeout: int = 15) -> dict[str, Any]:
    try:
        response = requests.get(
            "https://api.weixin.qq.com/sns/oauth2/access_token",
            params={
                "appid": app_id,
                "secret": app_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise WeChatOAuthRequestError(str(exc)) from exc


def fetch_wechat_userinfo(*, access_token: str, openid: str, timeout: int = 15) -> dict[str, Any]:
    try:
        response = requests.get(
            "https://api.weixin.qq.com/sns/userinfo",
            params={
                "access_token": access_token,
                "openid": openid,
                "lang": "zh_CN",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise WeChatOAuthRequestError(str(exc)) from exc
