from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import secrets
from typing import Any, Protocol

from aicrm_next.shared.repository_provider import RepositoryProviderError, assert_repository_allowed
from aicrm_next.shared.runtime import production_data_ready, raw_database_url


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


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


class PostgresRadarLinksRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = _psycopg_url(str(database_url or raw_database_url()).strip())
        if not self._database_url:
            raise RepositoryProviderError("radar_links production repository unavailable: DATABASE_URL is required")

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row

            return psycopg.connect(self._database_url, row_factory=dict_row)
        except Exception as exc:
            raise RepositoryProviderError(f"radar_links production repository unavailable: {exc}") from exc

    @staticmethod
    def _row(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return dict(row)

    def _new_code(self, conn) -> str:
        while True:
            code = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]
            exists = conn.execute("SELECT 1 FROM radar_links WHERE code = %s", (code,)).fetchone()
            if code and not exists:
                return code

    def list_links(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        limit = max(1, min(int(limit or 50), 200))
        offset = max(0, int(offset or 0))
        with self._connect() as conn:
            total = int((conn.execute("SELECT COUNT(*) AS total FROM radar_links").fetchone() or {}).get("total") or 0)
            rows = conn.execute(
                """
                SELECT id, code, title, original_url, enabled, auth_required, source_channel, campaign_id, staff_id, created_at, updated_at
                FROM radar_links
                ORDER BY id DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            ).fetchall()
        return [dict(row) for row in rows], total

    def get_link(self, link_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, code, title, original_url, enabled, auth_required, source_channel, campaign_id, staff_id, created_at, updated_at
                FROM radar_links
                WHERE id = %s
                """,
                (int(link_id),),
            ).fetchone()
        return self._row(row)

    def get_link_by_code(self, code: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, code, title, original_url, enabled, auth_required, source_channel, campaign_id, staff_id, created_at, updated_at
                FROM radar_links
                WHERE code = %s
                """,
                (str(code or "").strip(),),
            ).fetchone()
        return self._row(row)

    def save_link(self, payload: dict[str, Any], link_id: int | None = None) -> dict[str, Any]:
        with self._connect() as conn:
            if link_id is None:
                row = conn.execute(
                    """
                    INSERT INTO radar_links (
                        code, title, original_url, enabled, auth_required, source_channel, campaign_id, staff_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, code, title, original_url, enabled, auth_required, source_channel, campaign_id, staff_id, created_at, updated_at
                    """,
                    (
                        self._new_code(conn),
                        str(payload.get("title") or "").strip(),
                        str(payload.get("original_url") or "").strip(),
                        bool(payload.get("enabled", True)),
                        bool(payload.get("auth_required", False)),
                        str(payload.get("source_channel") or "").strip(),
                        str(payload.get("campaign_id") or "").strip(),
                        str(payload.get("staff_id") or "").strip(),
                    ),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    UPDATE radar_links
                    SET title = %s,
                        original_url = %s,
                        enabled = %s,
                        auth_required = %s,
                        source_channel = %s,
                        campaign_id = %s,
                        staff_id = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, code, title, original_url, enabled, auth_required, source_channel, campaign_id, staff_id, created_at, updated_at
                    """,
                    (
                        str(payload.get("title") or "").strip(),
                        str(payload.get("original_url") or "").strip(),
                        bool(payload.get("enabled", True)),
                        bool(payload.get("auth_required", False)),
                        str(payload.get("source_channel") or "").strip(),
                        str(payload.get("campaign_id") or "").strip(),
                        str(payload.get("staff_id") or "").strip(),
                        int(link_id),
                    ),
                ).fetchone()
        return dict(row or {})

    def set_enabled(self, link_id: int, enabled: bool) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE radar_links
                SET enabled = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING id, code, title, original_url, enabled, auth_required, source_channel, campaign_id, staff_id, created_at, updated_at
                """,
                (bool(enabled), int(link_id)),
            ).fetchone()
        return self._row(row)

    def record_click_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO radar_click_events (
                    link_id, code, stage, openid, unionid, external_userid,
                    source_channel, campaign_id, staff_id, user_agent, ip
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, id AS event_id, link_id, code, stage, openid, unionid, external_userid,
                    source_channel, campaign_id, staff_id, user_agent, ip, created_at
                """,
                (
                    int(payload.get("link_id") or 0),
                    str(payload.get("code") or ""),
                    str(payload.get("stage") or ""),
                    str(payload.get("openid") or ""),
                    str(payload.get("unionid") or ""),
                    str(payload.get("external_userid") or ""),
                    str(payload.get("source_channel") or ""),
                    str(payload.get("campaign_id") or ""),
                    str(payload.get("staff_id") or ""),
                    str(payload.get("user_agent") or ""),
                    str(payload.get("ip") or ""),
                ),
            ).fetchone()
        return dict(row or {})

    def list_click_events(self, link_id: int, *, limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        limit = max(1, min(int(limit or 100), 500))
        offset = max(0, int(offset or 0))
        with self._connect() as conn:
            total = int(
                (conn.execute("SELECT COUNT(*) AS total FROM radar_click_events WHERE link_id = %s", (int(link_id),)).fetchone() or {}).get("total") or 0
            )
            rows = conn.execute(
                """
                SELECT id, id AS event_id, link_id, code, stage, openid, unionid, external_userid,
                    source_channel, campaign_id, staff_id, user_agent, ip, created_at
                FROM radar_click_events
                WHERE link_id = %s
                ORDER BY id DESC
                LIMIT %s OFFSET %s
                """,
                (int(link_id), limit, offset),
            ).fetchall()
        return [dict(row) for row in rows], total

    def stats(self, link_id: int) -> dict[str, Any] | None:
        if not self.get_link(link_id):
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE stage = 'landing') AS total_clicks,
                    COUNT(*) FILTER (WHERE stage = 'authorized_click') AS authorized_clicks,
                    COUNT(DISTINCT NULLIF(COALESCE(NULLIF(unionid, ''), NULLIF(openid, ''), NULLIF(external_userid, '')), ''))
                        FILTER (WHERE stage = 'authorized_click') AS unique_users,
                    COUNT(*) FILTER (WHERE stage = 'landing' AND created_at::date = CURRENT_DATE) AS today_clicks,
                    MAX(created_at) FILTER (WHERE stage = 'landing') AS last_clicked_at
                FROM radar_click_events
                WHERE link_id = %s
                """,
                (int(link_id),),
            ).fetchone()
        return {
            "total_clicks": int((row or {}).get("total_clicks") or 0),
            "authorized_clicks": int((row or {}).get("authorized_clicks") or 0),
            "unique_users": int((row or {}).get("unique_users") or 0),
            "today_clicks": int((row or {}).get("today_clicks") or 0),
            "last_clicked_at": str((row or {}).get("last_clicked_at") or ""),
        }


_DEFAULT_REPO = InMemoryRadarLinksRepository()


def build_radar_links_repository() -> RadarLinksRepository:
    if production_data_ready():
        return PostgresRadarLinksRepository()
    return assert_repository_allowed(_DEFAULT_REPO, capability_owner="radar_links")


def reset_radar_links_fixture_state() -> None:
    _DEFAULT_REPO.reset()
