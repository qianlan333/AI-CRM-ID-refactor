from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import secrets
from typing import Any, Protocol

from aicrm_next.shared.repository_provider import assert_repository_allowed


class RadarLinksRepository(Protocol):
    def list_links(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]: ...
    def get_link(self, link_id: int) -> dict[str, Any] | None: ...
    def get_link_by_code(self, code: str) -> dict[str, Any] | None: ...
    def save_link(self, payload: dict[str, Any], link_id: int | None = None) -> dict[str, Any]: ...
    def set_enabled(self, link_id: int, enabled: bool) -> dict[str, Any] | None: ...
    def record_click_event(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def list_click_events(self, link_id: int, *, limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]: ...
    def stats(self, link_id: int) -> dict[str, Any] | None: ...


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _today_prefix() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class InMemoryRadarLinksRepository:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._links: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = []
        self._next_id = 1
        self._next_event_id = 1

    def _new_code(self) -> str:
        while True:
            code = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]
            if code and not self.get_link_by_code(code):
                return code

    def list_links(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        rows = deepcopy(sorted(self._links, key=lambda item: int(item["id"]), reverse=True))
        return rows[offset : offset + limit], len(rows)

    def get_link(self, link_id: int) -> dict[str, Any] | None:
        for item in self._links:
            if int(item["id"]) == int(link_id):
                return deepcopy(item)
        return None

    def get_link_by_code(self, code: str) -> dict[str, Any] | None:
        normalized = str(code or "").strip()
        for item in self._links:
            if item.get("code") == normalized:
                return deepcopy(item)
        return None

    def save_link(self, payload: dict[str, Any], link_id: int | None = None) -> dict[str, Any]:
        now = _now()
        if link_id is None:
            item = {
                "id": self._next_id,
                "code": self._new_code(),
                "created_at": now,
            }
            self._next_id += 1
            self._links.append(item)
        else:
            item = next((entry for entry in self._links if int(entry["id"]) == int(link_id)), None)
            if item is None:
                return {}
        item.update(
            {
                "title": str(payload.get("title", item.get("title", "")) or "").strip(),
                "original_url": str(payload.get("original_url", item.get("original_url", "")) or "").strip(),
                "enabled": bool(payload.get("enabled", item.get("enabled", True))),
                "auth_required": bool(payload.get("auth_required", item.get("auth_required", False))),
                "source_channel": str(payload.get("source_channel", item.get("source_channel", "")) or "").strip(),
                "campaign_id": str(payload.get("campaign_id", item.get("campaign_id", "")) or "").strip(),
                "staff_id": str(payload.get("staff_id", item.get("staff_id", "")) or "").strip(),
                "updated_at": now,
            }
        )
        return deepcopy(item)

    def set_enabled(self, link_id: int, enabled: bool) -> dict[str, Any] | None:
        item = next((entry for entry in self._links if int(entry["id"]) == int(link_id)), None)
        if item is None:
            return None
        item["enabled"] = bool(enabled)
        item["updated_at"] = _now()
        return deepcopy(item)

    def record_click_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = deepcopy(payload)
        event["id"] = self._next_event_id
        event["event_id"] = self._next_event_id
        event["created_at"] = event.get("created_at") or _now()
        self._next_event_id += 1
        self._events.append(event)
        return deepcopy(event)

    def list_click_events(self, link_id: int, *, limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        rows = [
            deepcopy(item)
            for item in reversed(self._events)
            if int(item.get("link_id") or 0) == int(link_id)
        ]
        return rows[offset : offset + limit], len(rows)

    def stats(self, link_id: int) -> dict[str, Any] | None:
        if not self.get_link(link_id):
            return None
        events = [item for item in self._events if int(item.get("link_id") or 0) == int(link_id)]
        landing_events = [item for item in events if item.get("stage") == "landing"]
        authorized_events = [item for item in events if item.get("stage") == "authorized_click"]
        unique_users = {
            str(item.get("unionid") or item.get("openid") or item.get("external_userid") or "").strip()
            for item in authorized_events
            if str(item.get("unionid") or item.get("openid") or item.get("external_userid") or "").strip()
        }
        today = _today_prefix()
        last_clicked_at = ""
        if landing_events:
            last_clicked_at = max(str(item.get("created_at") or "") for item in landing_events)
        return {
            "total_clicks": len(landing_events),
            "authorized_clicks": len(authorized_events),
            "unique_users": len(unique_users),
            "today_clicks": len([item for item in landing_events if str(item.get("created_at") or "").startswith(today)]),
            "last_clicked_at": last_clicked_at,
        }


_DEFAULT_REPO = InMemoryRadarLinksRepository()


def build_radar_links_repository() -> RadarLinksRepository:
    return assert_repository_allowed(_DEFAULT_REPO, capability_owner="radar_links")


def reset_radar_links_fixture_state() -> None:
    _DEFAULT_REPO.reset()

