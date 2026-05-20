from __future__ import annotations

from urllib.parse import quote

from .dto import OAuthCallbackRequest, OAuthStartRequest


class FakeWechatOAuthAdapter:
    source_status = "fake"

    def start(self, request: OAuthStartRequest) -> dict:
        state = (request.state or request.slug or "questionnaire_fake_state").strip()
        redirect_url = request.redirect or f"/api/h5/wechat/oauth/callback?state={quote(state)}"
        query = []
        if request.openid:
            query.append(f"openid={quote(request.openid)}")
        if request.unionid:
            query.append(f"unionid={quote(request.unionid)}")
        if request.external_userid:
            query.append(f"external_userid={quote(request.external_userid)}")
        fake_redirect_url = redirect_url + (("&" if "?" in redirect_url else "?") + "&".join(query) if query else "")
        return {
            "ok": True,
            "redirect_url": fake_redirect_url,
            "state": state,
            "source_status": self.source_status,
            "oauth_provider": "wechat_mp",
        }

    def callback(self, request: OAuthCallbackRequest) -> dict:
        state = (request.state or "").strip()
        redirect_url = request.redirect or (f"/s/{state}" if state else "/")
        return {
            "ok": True,
            "openid": request.openid or "openid_fake_001",
            "unionid": request.unionid or "unionid_fake_001",
            "external_userid": request.external_userid or "",
            "redirect_url": redirect_url,
            "state": state,
            "source_status": self.source_status if state else "missing_config",
        }
