from __future__ import annotations

import os
from typing import Any

from aicrm_next.integration_gateway.questionnaire_adapters import WeChatOAuthAdapter, build_wechat_oauth_adapter
from aicrm_next.shared.errors import ContractError, NotFoundError

from .domain import normalize_radar_link_payload, radar_link_projection, sign_radar_state, verify_radar_state
from .dto import RadarLinkCreateRequest, RadarLinkUpdateRequest
from .repo import RadarLinksRepository, build_radar_links_repository


def _secret_key() -> str:
    return os.getenv("SECRET_KEY", "").strip()


class ListRadarLinksQuery:
    def __init__(self, repo: RadarLinksRepository | None = None) -> None:
        self._repo = repo or build_radar_links_repository()

    def execute(self, *, base_url: str = "", limit: int = 50, offset: int = 0) -> dict[str, Any]:
        rows, total = self._repo.list_links(limit=limit, offset=offset)
        items = [radar_link_projection(item, base_url=base_url) for item in rows]
        return {"ok": True, "items": items, "radar_links": items, "total": total, "limit": limit, "offset": offset}

    __call__ = execute


class CreateRadarLinkCommand:
    def __init__(self, repo: RadarLinksRepository | None = None) -> None:
        self._repo = repo or build_radar_links_repository()

    def execute(self, payload: RadarLinkCreateRequest, *, base_url: str = "") -> dict[str, Any]:
        saved = self._repo.save_link(normalize_radar_link_payload(payload.model_dump()))
        return {"ok": True, "radar_link": radar_link_projection(saved, base_url=base_url)}

    __call__ = execute


class GetRadarLinkQuery:
    def __init__(self, repo: RadarLinksRepository | None = None) -> None:
        self._repo = repo or build_radar_links_repository()

    def execute(self, link_id: int, *, base_url: str = "") -> dict[str, Any]:
        item = self._repo.get_link(link_id)
        if not item:
            raise NotFoundError("radar link not found")
        return {"ok": True, "radar_link": radar_link_projection(item, base_url=base_url)}

    __call__ = execute


class UpdateRadarLinkCommand:
    def __init__(self, repo: RadarLinksRepository | None = None) -> None:
        self._repo = repo or build_radar_links_repository()

    def execute(self, link_id: int, payload: RadarLinkUpdateRequest, *, base_url: str = "") -> dict[str, Any]:
        updates = normalize_radar_link_payload(payload.model_dump(exclude_unset=True), partial=True)
        if not updates:
            item = self._repo.get_link(link_id)
        else:
            current = self._repo.get_link(link_id)
            if not current:
                item = None
            else:
                item = self._repo.save_link({**current, **updates}, link_id)
        if not item:
            raise NotFoundError("radar link not found")
        return {"ok": True, "radar_link": radar_link_projection(item, base_url=base_url)}

    __call__ = execute


class SetRadarLinkEnabledCommand:
    def __init__(self, repo: RadarLinksRepository | None = None) -> None:
        self._repo = repo or build_radar_links_repository()

    def execute(self, link_id: int, *, enabled: bool, base_url: str = "") -> dict[str, Any]:
        item = self._repo.set_enabled(link_id, enabled)
        if not item:
            raise NotFoundError("radar link not found")
        return {"ok": True, "radar_link": radar_link_projection(item, base_url=base_url)}

    __call__ = execute


class GetRadarLinkStatsQuery:
    def __init__(self, repo: RadarLinksRepository | None = None) -> None:
        self._repo = repo or build_radar_links_repository()

    def execute(self, link_id: int) -> dict[str, Any]:
        stats = self._repo.stats(link_id)
        if stats is None:
            raise NotFoundError("radar link not found")
        return {"ok": True, "stats": stats}

    __call__ = execute


class ListRadarLinkEventsQuery:
    def __init__(self, repo: RadarLinksRepository | None = None) -> None:
        self._repo = repo or build_radar_links_repository()

    def execute(self, link_id: int, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        if not self._repo.get_link(link_id):
            raise NotFoundError("radar link not found")
        events, total = self._repo.list_click_events(link_id, limit=limit, offset=offset)
        return {"ok": True, "items": events, "events": events, "total": total, "limit": limit, "offset": offset}

    __call__ = execute


class ResolveRadarLandingQuery:
    def __init__(self, repo: RadarLinksRepository | None = None) -> None:
        self._repo = repo or build_radar_links_repository()

    def execute(self, code: str, *, identity: dict[str, str], request_meta: dict[str, str]) -> dict[str, Any]:
        link = self._repo.get_link_by_code(code)
        if not link or not bool(link.get("enabled", True)):
            raise NotFoundError("radar link not found")
        self._record_event(link, stage="landing", identity=identity, request_meta=request_meta)
        has_identity = bool(identity.get("openid") or identity.get("unionid"))
        if bool(link.get("auth_required")) and not has_identity:
            state = sign_radar_state(code=str(link["code"]), secret_key=_secret_key())
            return {"ok": True, "action": "oauth_start", "oauth_start_url": f"/api/h5/radar/oauth/start?state={state}"}
        if has_identity:
            self._record_event(link, stage="authorized_click", identity=identity, request_meta=request_meta)
        return {"ok": True, "action": "redirect", "redirect_url": str(link.get("original_url") or "")}

    def _record_event(self, link: dict[str, Any], *, stage: str, identity: dict[str, str], request_meta: dict[str, str]) -> None:
        self._repo.record_click_event(
            {
                "link_id": int(link["id"]),
                "code": str(link.get("code") or ""),
                "stage": stage,
                "openid": identity.get("openid", ""),
                "unionid": identity.get("unionid", ""),
                "external_userid": identity.get("external_userid", ""),
                "source_channel": str(link.get("source_channel") or ""),
                "campaign_id": str(link.get("campaign_id") or ""),
                "staff_id": str(link.get("staff_id") or ""),
                "user_agent": request_meta.get("user_agent", ""),
                "ip": request_meta.get("ip", ""),
            }
        )

    __call__ = execute


class StartRadarOAuthQuery:
    def __init__(self, adapter: WeChatOAuthAdapter | None = None) -> None:
        self._adapter = adapter or build_wechat_oauth_adapter()

    def execute(self, *, state: str | None, code: str | None = None, openid: str | None = None, unionid: str | None = None, external_userid: str | None = None) -> dict[str, Any]:
        signed_state = str(state or "").strip() or sign_radar_state(code=str(code or ""), secret_key=_secret_key())
        context = verify_radar_state(signed_state, secret_key=_secret_key())
        callback_url = f"/api/h5/radar/oauth/callback?state={signed_state}"
        adapter_result = self._adapter.build_authorize_url(
            slug=str(context["code"]),
            state=signed_state,
            redirect=callback_url,
            openid=openid,
            unionid=unionid,
            external_userid=external_userid,
        )
        result = adapter_result.get("result") if isinstance(adapter_result.get("result"), dict) else {}
        if not adapter_result.get("ok"):
            raise ContractError(str(adapter_result.get("error_message") or "radar oauth adapter unavailable"))
        return {
            "ok": True,
            "redirect_url": result.get("redirect_url") or callback_url,
            "state": signed_state,
            "source_status": result.get("source_status", "fake"),
        }

    __call__ = execute


class CompleteRadarOAuthCallbackCommand:
    def __init__(self, repo: RadarLinksRepository | None = None, adapter: WeChatOAuthAdapter | None = None) -> None:
        self._repo = repo or build_radar_links_repository()
        self._adapter = adapter or build_wechat_oauth_adapter()

    def execute(
        self,
        *,
        state: str | None,
        code: str | None = None,
        openid: str | None = None,
        unionid: str | None = None,
        external_userid: str | None = None,
        request_meta: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        context = verify_radar_state(state, secret_key=_secret_key())
        link = self._repo.get_link_by_code(str(context["code"]))
        if not link or not bool(link.get("enabled", True)):
            raise NotFoundError("radar link not found")
        adapter_result = self._adapter.resolve_oauth_identity(
            state=state,
            code=code,
            openid=openid,
            unionid=unionid,
            external_userid=external_userid,
        )
        result = adapter_result.get("result") if isinstance(adapter_result.get("result"), dict) else {}
        if not adapter_result.get("ok"):
            raise ContractError(str(adapter_result.get("error_message") or "radar oauth adapter unavailable"))
        identity = {
            "openid": str(result.get("openid") or openid or ""),
            "unionid": str(result.get("unionid") or unionid or ""),
            "external_userid": str(result.get("external_userid") or external_userid or ""),
        }
        meta = request_meta or {}
        for stage in ("oauth_callback", "authorized_click"):
            self._repo.record_click_event(
                {
                    "link_id": int(link["id"]),
                    "code": str(link.get("code") or ""),
                    "stage": stage,
                    **identity,
                    "source_channel": str(link.get("source_channel") or ""),
                    "campaign_id": str(link.get("campaign_id") or ""),
                    "staff_id": str(link.get("staff_id") or ""),
                    "user_agent": meta.get("user_agent", ""),
                    "ip": meta.get("ip", ""),
                }
            )
        return {"ok": True, "redirect_url": str(link.get("original_url") or ""), "identity": identity, "source_status": result.get("source_status", "fake")}

    __call__ = execute
