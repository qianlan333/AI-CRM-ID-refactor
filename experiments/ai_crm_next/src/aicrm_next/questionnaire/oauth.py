from __future__ import annotations

from aicrm_next.integration_gateway.questionnaire_adapters import WeChatOAuthAdapter, build_wechat_oauth_adapter
from .dto import OAuthCallbackRequest, OAuthStartRequest


class FakeWechatOAuthAdapter:
    source_status = "fake"

    def __init__(self, adapter: WeChatOAuthAdapter | None = None) -> None:
        self._adapter = adapter or build_wechat_oauth_adapter()

    def start(self, request: OAuthStartRequest) -> dict:
        adapter_result = self._adapter.build_authorize_url(
            slug=request.slug,
            state=request.state,
            redirect=request.redirect,
            openid=request.openid,
            unionid=request.unionid,
            external_userid=request.external_userid,
        )
        result = adapter_result.get("result") if isinstance(adapter_result.get("result"), dict) else {}
        return {
            "ok": bool(adapter_result.get("ok")),
            "redirect_url": result.get("redirect_url", ""),
            "state": result.get("state", request.state or request.slug or ""),
            "source_status": result.get("source_status", "adapter_error"),
            "oauth_provider": result.get("oauth_provider", "wechat_mp"),
        }

    def callback(self, request: OAuthCallbackRequest) -> dict:
        adapter_result = self._adapter.resolve_oauth_identity(
            state=request.state,
            redirect=request.redirect,
            openid=request.openid,
            unionid=request.unionid,
            external_userid=request.external_userid,
        )
        result = adapter_result.get("result") if isinstance(adapter_result.get("result"), dict) else {}
        return {
            "ok": bool(adapter_result.get("ok")),
            "openid": result.get("openid", request.openid or "openid_fake_001"),
            "unionid": result.get("unionid", request.unionid or "unionid_fake_001"),
            "external_userid": result.get("external_userid", request.external_userid or ""),
            "redirect_url": result.get("redirect_url", request.redirect or (f"/s/{request.state}" if request.state else "/")),
            "state": result.get("state", request.state or ""),
            "source_status": result.get("source_status", "missing_config" if not request.state else "adapter_error"),
        }
