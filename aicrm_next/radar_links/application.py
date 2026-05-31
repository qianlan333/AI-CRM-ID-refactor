from __future__ import annotations

import base64
import os
from typing import Any

from aicrm_next.integration_gateway.questionnaire_adapters import WeChatOAuthAdapter, build_wechat_oauth_adapter
from aicrm_next.media_library.application import GetMediaItemQuery
from aicrm_next.shared.errors import ContractError, NotFoundError

from .domain import (
    hash_ip,
    normalize_radar_link_payload,
    normalize_target_type,
    radar_link_projection,
    sign_radar_state,
    sign_viewer_session,
    validate_media_for_target,
    verify_radar_state,
    verify_viewer_session,
)
from .dto import RadarLinkCreateRequest, RadarLinkUpdateRequest
from .repo import RadarLinksRepository, build_radar_links_repository


def _secret_key() -> str:
    return os.getenv("SECRET_KEY", "").strip()


class ListRadarLinksQuery:
    def __init__(self, repo: RadarLinksRepository | None = None) -> None:
        self._repo = repo or build_radar_links_repository()

    def execute(self, *, base_url: str = "", limit: int = 50, offset: int = 0) -> dict[str, Any]:
        rows, total = self._repo.list_links(limit=limit, offset=offset)
        items = []
        for item in rows:
            projection = radar_link_projection(item, base_url=base_url)
            stats = self._repo.stats(int(item.get("id") or 0)) or {}
            projection["stats_summary"] = {
                "total_landings": int(stats.get("total_landings") or stats.get("total_clicks") or 0),
                "authorized_users": int(stats.get("authorized_users") or stats.get("unique_users") or 0),
                "view_opens": int(stats.get("view_opens") or stats.get("viewer_opens") or 0),
                "last_viewed_at": str(stats.get("last_viewed_at") or ""),
            }
            items.append(projection)
        return {"ok": True, "items": items, "radar_links": items, "total": total, "limit": limit, "offset": offset}

    __call__ = execute


class CreateRadarLinkCommand:
    def __init__(self, repo: RadarLinksRepository | None = None) -> None:
        self._repo = repo or build_radar_links_repository()

    def execute(self, payload: RadarLinkCreateRequest, *, base_url: str = "") -> dict[str, Any]:
        saved = self._repo.save_link(_normalize_with_media(payload.model_dump()))
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
        raw_updates = payload.model_dump(exclude_unset=True)
        updates = normalize_radar_link_payload(raw_updates, partial=True)
        if not updates:
            item = self._repo.get_link(link_id)
        else:
            current = self._repo.get_link(link_id)
            if not current:
                item = None
            else:
                item = self._repo.save_link(_normalize_with_media({**current, **updates}), link_id)
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
        link = self._repo.get_link(link_id)
        stats = self._repo.stats(link_id)
        if stats is None:
            raise NotFoundError("radar link not found")
        return {"ok": True, "link_id": link_id, "target_type": normalize_target_type(str((link or {}).get("target_type") or "link")), "stats": stats, **stats}

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

    def execute(self, code: str, *, identity: dict[str, str], request_meta: dict[str, Any], viewer_session: str | None = None) -> dict[str, Any]:
        link = self._repo.get_link_by_code(code)
        if not link or not bool(link.get("enabled", True)):
            raise NotFoundError("radar link not found")
        self._record_event(link, stage="landing", identity=identity, request_meta=request_meta)
        has_identity = bool(identity.get("openid") or identity.get("unionid"))
        has_session = False
        try:
            verify_viewer_session(viewer_session, code=str(link["code"]), secret_key=_secret_key())
            has_session = True
        except ContractError:
            has_session = False
        if bool(link.get("auth_required")) and not has_identity and not has_session:
            state = sign_radar_state(code=str(link["code"]), secret_key=_secret_key())
            self._record_event(link, stage="oauth_start", identity=identity, request_meta=request_meta)
            return {"ok": True, "action": "oauth_start", "oauth_start_url": f"/api/h5/radar/oauth/start?state={state}"}
        target_type = normalize_target_type(str(link.get("target_type") or "link"))
        viewer_token = ""
        if target_type in {"image", "pdf"} and not has_session:
            viewer_token = sign_viewer_session(code=str(link["code"]), **identity, secret_key=_secret_key())
        if target_type == "link":
            self._record_event(link, stage="redirect", identity=identity, request_meta=request_meta)
            return {"ok": True, "action": "redirect", "redirect_url": str(link.get("original_url") or ""), "viewer_session_token": viewer_token}
        return {"ok": True, "action": "redirect", "redirect_url": f"/radar/view/{link['code']}", "viewer_session_token": viewer_token}

    def _record_event(self, link: dict[str, Any], *, stage: str, identity: dict[str, str], request_meta: dict[str, Any]) -> None:
        self._repo.record_click_event(
            {
                "link_id": int(link["id"]),
                "code": str(link.get("code") or ""),
                "target_type_snapshot": normalize_target_type(str(link.get("target_type") or "link")),
                "stage": stage,
                "openid": identity.get("openid", ""),
                "unionid": identity.get("unionid", ""),
                "external_userid": identity.get("external_userid", ""),
                "source_channel": str(link.get("source_channel") or ""),
                "campaign_id": str(link.get("campaign_id") or ""),
                "staff_id": str(link.get("staff_id") or ""),
                "source_channel_snapshot": str(link.get("source_channel") or ""),
                "campaign_id_snapshot": str(link.get("campaign_id") or ""),
                "staff_id_snapshot": str(link.get("staff_id") or ""),
                "user_agent": request_meta.get("user_agent", ""),
                "ip_hash": hash_ip(str(request_meta.get("ip") or ""), secret_key=_secret_key()),
                "referer": request_meta.get("referer", ""),
                "query_params_json": request_meta.get("query_params_json") if isinstance(request_meta.get("query_params_json"), dict) else {},
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
        for stage in ("oauth_callback", "authorized"):
            self._repo.record_click_event(
                {
                    "link_id": int(link["id"]),
                    "code": str(link.get("code") or ""),
                    "target_type_snapshot": normalize_target_type(str(link.get("target_type") or "link")),
                    "stage": stage,
                    **identity,
                    "source_channel": str(link.get("source_channel") or ""),
                    "campaign_id": str(link.get("campaign_id") or ""),
                    "staff_id": str(link.get("staff_id") or ""),
                    "source_channel_snapshot": str(link.get("source_channel") or ""),
                    "campaign_id_snapshot": str(link.get("campaign_id") or ""),
                    "staff_id_snapshot": str(link.get("staff_id") or ""),
                    "user_agent": meta.get("user_agent", ""),
                    "ip_hash": hash_ip(str(meta.get("ip") or ""), secret_key=_secret_key()),
                    "referer": meta.get("referer", ""),
                    "query_params_json": meta.get("query_params_json") if isinstance(meta.get("query_params_json"), dict) else {},
                }
            )
        target_type = normalize_target_type(str(link.get("target_type") or "link"))
        viewer_token = sign_viewer_session(code=str(link["code"]), **identity, secret_key=_secret_key())
        redirect_url = str(link.get("original_url") or "") if target_type == "link" else f"/radar/view/{link['code']}"
        if target_type == "link":
            self._repo.record_click_event(
                {
                    "link_id": int(link["id"]),
                    "code": str(link.get("code") or ""),
                    "target_type_snapshot": target_type,
                    "stage": "redirect",
                    **identity,
                    "source_channel": str(link.get("source_channel") or ""),
                    "campaign_id": str(link.get("campaign_id") or ""),
                    "staff_id": str(link.get("staff_id") or ""),
                    "source_channel_snapshot": str(link.get("source_channel") or ""),
                    "campaign_id_snapshot": str(link.get("campaign_id") or ""),
                    "staff_id_snapshot": str(link.get("staff_id") or ""),
                    "user_agent": meta.get("user_agent", ""),
                    "ip_hash": hash_ip(str(meta.get("ip") or ""), secret_key=_secret_key()),
                    "referer": meta.get("referer", ""),
                    "query_params_json": meta.get("query_params_json") if isinstance(meta.get("query_params_json"), dict) else {},
                }
            )
        return {"ok": True, "redirect_url": redirect_url, "identity": identity, "source_status": result.get("source_status", "fake"), "viewer_session_token": viewer_token}

    __call__ = execute


class GetRadarViewerPageQuery:
    def __init__(self, repo: RadarLinksRepository | None = None) -> None:
        self._repo = repo or build_radar_links_repository()

    def execute(self, code: str, *, viewer_session: str | None, request_meta: dict[str, Any]) -> dict[str, Any]:
        link = _require_viewable_content(self._repo, code, viewer_session)
        self._record_view_event(link, "viewer_open", request_meta=request_meta)
        return {"ok": True, "radar_link": radar_link_projection(link), "target_type": normalize_target_type(str(link.get("target_type") or "link"))}

    def _record_view_event(self, link: dict[str, Any], stage: str, *, request_meta: dict[str, Any]) -> None:
        self._repo.record_click_event(_view_event_payload(link, stage=stage, request_meta=request_meta))

    __call__ = execute


class GetRadarContentResourceQuery:
    def __init__(self, repo: RadarLinksRepository | None = None) -> None:
        self._repo = repo or build_radar_links_repository()

    def execute(self, code: str, *, target_type: str, viewer_session: str | None, request_meta: dict[str, Any]) -> dict[str, Any]:
        link = _require_viewable_content(self._repo, code, viewer_session)
        resolved_target_type = normalize_target_type(str(link.get("target_type") or "link"))
        if resolved_target_type != target_type:
            raise NotFoundError("radar content not found")
        media_kind = "image" if target_type == "image" else "attachment"
        media_id = str(link.get("media_item_id") or "").strip()
        item = GetMediaItemQuery(media_kind)(media_id, include_data=True)["item"]
        data_base64 = str(item.get("data_base64") or "")
        if not data_base64:
            raise NotFoundError("radar content data not found")
        try:
            content = base64.b64decode(data_base64)
        except Exception as exc:
            raise ContractError("radar content data is invalid") from exc
        stage = "image_loaded" if target_type == "image" else "pdf_opened"
        self._repo.record_click_event(_view_event_payload(link, stage=stage, request_meta=request_meta))
        mime_type = str(item.get("mime_type") or link.get("mime_type_snapshot") or ("image/png" if target_type == "image" else "application/pdf"))
        return {
            "ok": True,
            "content": content,
            "mime_type": mime_type,
            "file_name": str(item.get("file_name") or link.get("file_name_snapshot") or ("image" if target_type == "image" else "content.pdf")),
        }

    __call__ = execute


class RecordRadarContentEventCommand:
    ALLOWED_STAGES = {"viewer_open", "image_loaded", "pdf_opened"}

    def __init__(self, repo: RadarLinksRepository | None = None) -> None:
        self._repo = repo or build_radar_links_repository()

    def execute(self, code: str, *, payload: dict[str, Any], viewer_session: str | None, request_meta: dict[str, Any]) -> dict[str, Any]:
        stage = str(payload.get("stage") or "").strip()
        if stage not in self.ALLOWED_STAGES:
            raise ContractError("radar content event stage is not allowed")
        link = _require_viewable_content(self._repo, code, viewer_session)
        target_type = normalize_target_type(str(link.get("target_type") or "link"))
        if stage == "image_loaded" and target_type != "image":
            raise ContractError("image_loaded is only allowed for image radar content")
        if stage == "pdf_opened" and target_type != "pdf":
            raise ContractError("pdf_opened is only allowed for pdf radar content")
        event_payload = _view_event_payload(link, stage=stage, request_meta=request_meta)
        event_payload["query_params_json"] = {
            "page": payload.get("page"),
            "extra": payload.get("extra") if isinstance(payload.get("extra"), dict) else {},
        }
        event = self._repo.record_click_event(event_payload)
        return {"ok": True, "event_id": event.get("event_id") or event.get("id")}

    __call__ = execute


def _normalize_with_media(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_radar_link_payload(payload)
    target_type = normalize_target_type(str(normalized.get("target_type") or payload.get("target_type") or "link"))
    if target_type == "link":
        normalized.update({"media_item_id": "", "preview_mode": "", "file_name_snapshot": "", "mime_type_snapshot": "", "file_size_snapshot": 0})
        return normalized
    media_id = str(normalized.get("media_item_id") or payload.get("media_item_id") or "").strip()
    media_kind = "image" if target_type == "image" else "attachment"
    media_item = GetMediaItemQuery(media_kind)(media_id, include_data=False)["item"] if media_id else None
    normalized.update(validate_media_for_target(target_type, media_item))
    normalized["original_url"] = ""
    normalized["preview_mode"] = str(normalized.get("preview_mode") or ("inline_image" if target_type == "image" else "inline_pdf"))
    return normalized


def _require_viewable_content(repo: RadarLinksRepository, code: str, viewer_session: str | None) -> dict[str, Any]:
    link = repo.get_link_by_code(code)
    if not link or not bool(link.get("enabled", True)):
        raise NotFoundError("radar content not found")
    target_type = normalize_target_type(str(link.get("target_type") or "link"))
    if target_type not in {"image", "pdf"}:
        raise NotFoundError("radar content not found")
    verify_viewer_session(viewer_session, code=str(link["code"]), secret_key=_secret_key())
    return link


def _view_event_payload(link: dict[str, Any], *, stage: str, request_meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "link_id": int(link["id"]),
        "code": str(link.get("code") or ""),
        "target_type_snapshot": normalize_target_type(str(link.get("target_type") or "link")),
        "stage": stage,
        "openid": "",
        "unionid": "",
        "external_userid": "",
        "source_channel": str(link.get("source_channel") or ""),
        "campaign_id": str(link.get("campaign_id") or ""),
        "staff_id": str(link.get("staff_id") or ""),
        "source_channel_snapshot": str(link.get("source_channel") or ""),
        "campaign_id_snapshot": str(link.get("campaign_id") or ""),
        "staff_id_snapshot": str(link.get("staff_id") or ""),
        "user_agent": request_meta.get("user_agent", ""),
        "ip_hash": hash_ip(str(request_meta.get("ip") or ""), secret_key=_secret_key()),
        "referer": request_meta.get("referer", ""),
        "query_params_json": request_meta.get("query_params_json") if isinstance(request_meta.get("query_params_json"), dict) else {},
    }
