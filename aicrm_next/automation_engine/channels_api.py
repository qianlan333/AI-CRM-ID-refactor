from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse

from aicrm_next.common_operation_members import search_operation_members
from aicrm_next.shared.runtime import raw_database_url

router = APIRouter()

_FIXTURE_CHANNELS: dict[int, dict[str, Any]] = {}
_NEXT_ID = 1


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def _connect():
    database_url = _psycopg_url(raw_database_url())
    if not database_url.startswith(("postgresql://", "postgres://")):
        return None
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(database_url, row_factory=dict_row)


def _iso(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _json_list(value: Any) -> list[int]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        source = value
    elif isinstance(value, str):
        try:
            source = json.loads(value)
        except ValueError:
            source = []
    else:
        source = []
    result: list[int] = []
    for item in source:
        try:
            item_id = int(item)
        except (TypeError, ValueError):
            continue
        if item_id > 0 and item_id not in result:
            result.append(item_id)
    return result[:9]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _channel_type(payload: dict[str, Any]) -> tuple[str, str]:
    channel_type = _text(payload.get("channel_type")) or "qrcode"
    carrier_type = _text(payload.get("carrier_type")) or ("link" if channel_type == "wecom_customer_acquisition" else "qrcode")
    if channel_type == "wecom_customer_acquisition" or carrier_type == "link":
        return "wecom_customer_acquisition", "link"
    return "qrcode", "qrcode"


def _serialize_channel(row: dict[str, Any]) -> dict[str, Any]:
    channel = dict(row)
    channel_type, carrier_type = _channel_type(channel)
    channel["id"] = int(channel.get("id") or 0)
    channel["channel_type"] = channel_type
    channel["carrier_type"] = carrier_type
    channel["channel_code"] = _text(channel.get("channel_code"))
    channel["channel_name"] = _text(channel.get("channel_name"))
    channel["scene_value"] = _text(channel.get("scene_value"))
    channel["qr_url"] = _text(channel.get("qr_url"))
    channel["customer_channel"] = _text(channel.get("customer_channel"))
    channel["link_url"] = _text(channel.get("link_url"))
    channel["final_url"] = _text(channel.get("final_url"))
    if carrier_type == "link":
        channel["customer_channel"] = channel["customer_channel"] or _text(channel.get("wca_customer_channel"))
        channel["link_url"] = channel["link_url"] or _text(channel.get("wca_link_url"))
        channel["final_url"] = channel["final_url"] or _text(channel.get("wca_final_url"))
    channel["share_url"] = channel.get("share_url") or channel["final_url"] or channel["link_url"]
    channel["copy_text"] = channel.get("copy_text") or channel["share_url"] or channel["qr_url"]
    channel["welcome_message"] = _text(channel.get("welcome_message"))
    channel["welcome_image_library_ids"] = _json_list(channel.get("welcome_image_library_ids"))
    channel["welcome_miniprogram_library_ids"] = _json_list(channel.get("welcome_miniprogram_library_ids"))
    channel["welcome_attachment_library_ids"] = _json_list(channel.get("welcome_attachment_library_ids"))
    channel["welcome_attachment_count"] = len(channel["welcome_image_library_ids"]) + len(channel["welcome_miniprogram_library_ids"]) + len(channel["welcome_attachment_library_ids"])
    channel["welcome_message_configured"] = bool(channel["welcome_message"])
    channel["entry_tag_id"] = _text(channel.get("entry_tag_id"))
    channel["entry_tag_name"] = _text(channel.get("entry_tag_name"))
    channel["entry_tag_group_name"] = _text(channel.get("entry_tag_group_name"))
    channel["entry_tag_configured"] = bool(channel["entry_tag_id"] or channel["entry_tag_name"])
    channel["status"] = _text(channel.get("status")) or "active"
    channel["owner_staff_id"] = _text(channel.get("owner_staff_id"))
    channel["channel_contact_count"] = int(channel.get("channel_contact_count") or 0)
    channel["latest_channel_entered_at"] = _iso(channel.get("latest_channel_entered_at"))
    channel["bound_program_name"] = _text(channel.get("bound_program_name"))
    channel["qr_download_url"] = f"/api/admin/channels/{channel['id']}/qrcode/download" if carrier_type != "link" and channel["id"] else ""
    channel["created_at"] = _iso(channel.get("created_at"))
    channel["updated_at"] = _iso(channel.get("updated_at"))
    return channel


def _default_channel() -> dict[str, Any]:
    return {
        "channel_type": "qrcode",
        "carrier_type": "qrcode",
        "status": "active",
        "welcome_image_library_ids": [],
        "welcome_miniprogram_library_ids": [],
        "welcome_attachment_library_ids": [],
    }


def get_channel_resource(channel_id: int) -> dict[str, Any] | None:
    conn = _connect()
    if conn is None:
        channel = _FIXTURE_CHANNELS.get(int(channel_id))
        return _serialize_channel(channel) if channel else None
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.*,
                       COALESCE(contact_stats.channel_contact_count, 0) AS channel_contact_count,
                       contact_stats.latest_channel_entered_at,
                       binding.program_name AS bound_program_name,
                       wca.customer_channel AS wca_customer_channel,
                       wca.link_url AS wca_link_url,
                       wca.final_url AS wca_final_url
                FROM automation_channel c
                LEFT JOIN (
                    SELECT channel_id, count(*) AS channel_contact_count, max(last_channel_entered_at) AS latest_channel_entered_at
                    FROM automation_channel_contact
                    GROUP BY channel_id
                ) contact_stats ON contact_stats.channel_id = c.id
                LEFT JOIN (
                    SELECT DISTINCT ON (b.channel_id)
                           b.channel_id, p.program_name
                    FROM automation_program_channel_binding b
                    LEFT JOIN automation_program p ON p.id = b.program_id
                    WHERE b.binding_status = 'active'
                    ORDER BY b.channel_id, b.priority DESC, b.id DESC
                ) binding ON binding.channel_id = c.id
                LEFT JOIN wecom_customer_acquisition_links wca
                  ON wca.automation_channel_id = c.id AND wca.status = 'active'
                WHERE c.id = %s
                """,
                (int(channel_id),),
            )
            row = cur.fetchone()
    return _serialize_channel(dict(row)) if row else None


def _list_channels_from_postgres(*, limit: int, status: str = "", available_for_program_id: int | None = None) -> list[dict[str, Any]]:
    conn = _connect()
    if conn is None:
        channels = [_serialize_channel(item) for item in _FIXTURE_CHANNELS.values()]
        if status:
            channels = [item for item in channels if item.get("status") == status]
        return sorted(channels, key=lambda item: int(item.get("id") or 0), reverse=True)[:limit]
    params: list[Any] = []
    where = ""
    if status:
        where = "WHERE c.status = %s"
        params.append(status)
    if int(available_for_program_id or 0) > 0:
        where = where + (" AND " if where else "WHERE ")
        where += """
            NOT EXISTS (
                SELECT 1
                FROM automation_program_channel_binding active_b
                WHERE active_b.channel_id = c.id
                  AND active_b.binding_status = 'active'
            )
        """
    params.append(limit)
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT c.*,
                       COALESCE(contact_stats.channel_contact_count, 0) AS channel_contact_count,
                       contact_stats.latest_channel_entered_at,
                       binding.program_name AS bound_program_name,
                       wca.customer_channel AS wca_customer_channel,
                       wca.link_url AS wca_link_url,
                       wca.final_url AS wca_final_url
                FROM automation_channel c
                LEFT JOIN (
                    SELECT channel_id, count(*) AS channel_contact_count, max(last_channel_entered_at) AS latest_channel_entered_at
                    FROM automation_channel_contact
                    GROUP BY channel_id
                ) contact_stats ON contact_stats.channel_id = c.id
                LEFT JOIN (
                    SELECT DISTINCT ON (b.channel_id)
                           b.channel_id, p.program_name
                    FROM automation_program_channel_binding b
                    LEFT JOIN automation_program p ON p.id = b.program_id
                    WHERE b.binding_status = 'active'
                    ORDER BY b.channel_id, b.priority DESC, b.id DESC
                ) binding ON binding.channel_id = c.id
                LEFT JOIN wecom_customer_acquisition_links wca
                  ON wca.automation_channel_id = c.id AND wca.status = 'active'
                {where}
                ORDER BY c.updated_at DESC, c.id DESC
                LIMIT %s
                """,
                tuple(params),
            )
            return [_serialize_channel(dict(row)) for row in cur.fetchall() or []]


def _coerce_channel_payload(payload: dict[str, Any], *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    channel_type, carrier_type = _channel_type(payload)
    existing = existing or {}
    customer_channel = _text(payload.get("customer_channel") or payload.get("scene_value"))
    channel_code = _text(payload.get("channel_code")) or _text(existing.get("channel_code"))
    scene_value = customer_channel if carrier_type == "link" else _text(existing.get("scene_value") or payload.get("scene_value") or channel_code)
    final_url = _text(payload.get("final_url"))
    link_url = _text(payload.get("link_url"))
    if carrier_type == "link" and link_url and customer_channel and not final_url:
        separator = "&" if "?" in link_url else "?"
        final_url = f"{link_url}{separator}customer_channel={customer_channel}"
    return {
        "channel_type": channel_type,
        "carrier_type": carrier_type,
        "channel_name": _text(payload.get("channel_name")) or _text(existing.get("channel_name")) or channel_code or "未命名渠道",
        "channel_code": channel_code,
        "scene_value": scene_value,
        "qr_url": _text(existing.get("qr_url") or payload.get("qr_url")),
        "status": _text(payload.get("status")) or _text(existing.get("status")) or "active",
        "owner_staff_id": _text(payload.get("owner_staff_id") or existing.get("owner_staff_id")),
        "customer_channel": customer_channel if carrier_type == "link" else "",
        "link_url": link_url if carrier_type == "link" else "",
        "final_url": final_url if carrier_type == "link" else "",
        "welcome_message": _text(payload.get("welcome_message")),
        "welcome_image_library_ids": _json_list(payload.get("welcome_image_library_ids")),
        "welcome_miniprogram_library_ids": _json_list(payload.get("welcome_miniprogram_library_ids")),
        "welcome_attachment_library_ids": _json_list(payload.get("welcome_attachment_library_ids")),
        "entry_tag_id": _text(payload.get("entry_tag_id")),
        "entry_tag_name": _text(payload.get("entry_tag_name")),
        "entry_tag_group_name": _text(payload.get("entry_tag_group_name")),
    }


def _save_fixture_channel(payload: dict[str, Any], channel_id: int | None = None) -> dict[str, Any]:
    global _NEXT_ID
    existing = _FIXTURE_CHANNELS.get(int(channel_id or 0), {}) if channel_id else {}
    data = _coerce_channel_payload(payload, existing=existing)
    if channel_id is None:
        channel_id = _NEXT_ID
        _NEXT_ID += 1
    now = datetime.now(UTC).isoformat()
    channel = {**existing, **data, "id": int(channel_id), "updated_at": now, "created_at": existing.get("created_at") or now}
    _FIXTURE_CHANNELS[int(channel_id)] = channel
    return _serialize_channel(channel)


def _save_postgres_channel(payload: dict[str, Any], channel_id: int | None = None) -> dict[str, Any]:
    existing = get_channel_resource(int(channel_id)) if channel_id else None
    if channel_id and not existing:
        raise LookupError("channel_not_found")
    data = _coerce_channel_payload(payload, existing=existing)
    conn = _connect()
    if conn is None:
        return _save_fixture_channel(payload, channel_id)
    from psycopg.types.json import Jsonb

    columns = [
        "channel_type",
        "carrier_type",
        "channel_name",
        "channel_code",
        "scene_value",
        "qr_url",
        "status",
        "owner_staff_id",
        "customer_channel",
        "link_url",
        "final_url",
        "welcome_message",
        "welcome_image_library_ids",
        "welcome_miniprogram_library_ids",
        "welcome_attachment_library_ids",
        "entry_tag_id",
        "entry_tag_name",
        "entry_tag_group_name",
    ]
    values = [Jsonb(data[key]) if key.endswith("_ids") else data[key] for key in columns]
    with conn:
        with conn.cursor() as cur:
            if channel_id:
                assignments = ", ".join(f"{column} = %s" for column in columns)
                cur.execute(
                    f"UPDATE automation_channel SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING id",
                    tuple(values + [int(channel_id)]),
                )
                saved_id = int((cur.fetchone() or {}).get("id") or channel_id)
            else:
                placeholders = ", ".join(["%s"] * len(columns))
                cur.execute(
                    f"INSERT INTO automation_channel ({', '.join(columns)}) VALUES ({placeholders}) RETURNING id",
                    tuple(values),
                )
                saved_id = int((cur.fetchone() or {}).get("id") or 0)
        conn.commit()
    return get_channel_resource(saved_id) or {"id": saved_id, **data}


def list_channel_owner_candidates() -> list[dict[str, Any]]:
    # Compatibility wrapper for older channel-code callers. The page-level picker
    # now calls /api/admin/common/operation-members directly.
    payload = search_operation_members(scope="channel_code", page_size=100)
    return [
        {
            "owner_staff_id": item["user_id"],
            "display_name": item["display_name"] or item["user_id"],
            "position": _text((item.get("extra") or {}).get("position") or (item.get("extra") or {}).get("role")),
            "source": item.get("source") or "",
        }
        for item in payload.get("items", [])
    ]


def default_channel_form_payload() -> dict[str, Any]:
    return _default_channel()


@router.get("/api/admin/channels")
def list_channels(limit: int = Query(100), status: str = "", available_for_program_id: int | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "channels": _list_channels_from_postgres(
            limit=max(1, min(int(limit or 100), 500)),
            status=_text(status),
            available_for_program_id=available_for_program_id,
        ),
        "reason": "channels_listed",
        "source": "ai_crm_next",
    }


@router.post("/api/admin/channels", status_code=201)
def create_channel(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        channel = _save_postgres_channel(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "channel": channel, "reason": "channel_created", "source": "ai_crm_next"}


@router.get("/api/admin/channels/{channel_id:int}")
def get_channel(channel_id: int) -> dict[str, Any]:
    channel = get_channel_resource(int(channel_id))
    if not channel:
        raise HTTPException(status_code=404, detail="channel_not_found")
    return {"ok": True, "channel": channel, "reason": "channel_loaded", "source": "ai_crm_next"}


@router.patch("/api/admin/channels/{channel_id:int}")
def update_channel(channel_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        channel = _save_postgres_channel(payload, int(channel_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "channel": channel, "reason": "channel_updated", "source": "ai_crm_next"}


@router.get("/api/admin/channels/{channel_id:int}/contacts")
def list_channel_contacts(channel_id: int, limit: int = Query(100)) -> dict[str, Any]:
    conn = _connect()
    if conn is None:
        return {"ok": True, "contacts": [], "reason": "channel_contacts_listed", "source": "ai_crm_next"}
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT external_contact_id, display_name, enter_count, last_channel_entered_at
                FROM automation_channel_contact
                WHERE channel_id = %s
                ORDER BY last_channel_entered_at DESC, id DESC
                LIMIT %s
                """,
                (int(channel_id), max(1, min(int(limit or 100), 500))),
            )
            contacts = [{**dict(row), "last_channel_entered_at": _iso(row.get("last_channel_entered_at"))} for row in cur.fetchall() or []]
    return {"ok": True, "contacts": contacts, "reason": "channel_contacts_listed", "source": "ai_crm_next"}


@router.get("/api/admin/channels/{channel_id:int}/bindings")
def list_channel_bindings(channel_id: int) -> dict[str, Any]:
    conn = _connect()
    if conn is None:
        return {"ok": True, "bindings": [], "reason": "channel_bindings_listed", "source": "ai_crm_next"}
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT b.id, b.program_id, p.program_name, b.binding_status, b.priority
                FROM automation_program_channel_binding b
                LEFT JOIN automation_program p ON p.id = b.program_id
                WHERE b.channel_id = %s
                ORDER BY b.priority DESC, b.id DESC
                """,
                (int(channel_id),),
            )
            bindings = [dict(row) for row in cur.fetchall() or []]
    return {"ok": True, "bindings": bindings, "reason": "channel_bindings_listed", "source": "ai_crm_next"}


@router.get("/api/admin/channels/{channel_id:int}/share-link")
def get_channel_share_link(channel_id: int) -> dict[str, Any]:
    channel = get_channel_resource(int(channel_id))
    if not channel:
        raise HTTPException(status_code=404, detail="channel_not_found")
    if channel.get("carrier_type") != "link" and channel.get("channel_type") != "wecom_customer_acquisition":
        raise HTTPException(status_code=400, detail="channel_is_not_link_carrier")
    share_url = _text(channel.get("share_url") or channel.get("copy_text") or channel.get("final_url") or channel.get("link_url"))
    return {"ok": True, "share_url": share_url, "copy_text": share_url, "reason": "share_link_loaded", "source": "ai_crm_next"}


@router.get("/api/admin/channels/{channel_id:int}/qrcode/download")
def download_channel_qrcode(channel_id: int):
    channel = get_channel_resource(int(channel_id))
    if not channel:
        raise HTTPException(status_code=404, detail="channel_not_found")
    if channel.get("carrier_type") == "link" or channel.get("channel_type") == "wecom_customer_acquisition":
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "link channel does not support qrcode download", "reason": "link_channel_does_not_support_qrcode_download"},
        )
    qr_url = _text(channel.get("qr_url"))
    if qr_url.startswith(("http://", "https://")):
        return RedirectResponse(qr_url, status_code=302)
    raise HTTPException(status_code=404, detail="qrcode_not_ready")


@router.get("/api/admin/channel-welcome-materials")
def list_channel_welcome_materials(type: str = "all", keyword: str = "", q: str = "") -> dict[str, Any]:
    material_type = _text(type).lower() or "all"
    keyword_text = (_text(keyword) or _text(q)).lower()
    conn = _connect()
    if conn is None:
        return {"ok": True, "materials": [], "reason": "channel_welcome_materials_listed", "source": "ai_crm_next"}
    items: list[dict[str, Any]] = []
    with conn:
        with conn.cursor() as cur:
            if material_type in {"all", "miniprogram"}:
                cur.execute("SELECT id, name, title, appid, pagepath FROM miniprogram_library WHERE enabled = TRUE ORDER BY updated_at DESC, id DESC LIMIT 200")
                for row in cur.fetchall() or []:
                    haystack = " ".join(_text(row.get(key)) for key in ("name", "title", "appid", "pagepath")).lower()
                    if keyword_text and keyword_text not in haystack:
                        continue
                    name = _text(row.get("title") or row.get("name"))
                    items.append({"id": int(row["id"]), "type": "miniprogram", "name": name, "title": name, "description": _text(row.get("pagepath") or row.get("appid"))})
            if material_type in {"all", "image"}:
                cur.execute("SELECT id, name, file_name, mime_type FROM image_library WHERE enabled = TRUE ORDER BY updated_at DESC, id DESC LIMIT 200")
                for row in cur.fetchall() or []:
                    haystack = " ".join(_text(row.get(key)) for key in ("name", "file_name", "mime_type")).lower()
                    if keyword_text and keyword_text not in haystack:
                        continue
                    name = _text(row.get("name") or row.get("file_name"))
                    items.append({"id": int(row["id"]), "type": "image", "library": "image_library", "name": name, "title": name, "description": _text(row.get("file_name") or row.get("mime_type")), "mime_type": _text(row.get("mime_type"))})
            if material_type in {"all", "pdf"}:
                cur.execute("SELECT id, name, file_name, mime_type FROM attachment_library WHERE enabled = TRUE ORDER BY updated_at DESC, id DESC LIMIT 200")
                for row in cur.fetchall() or []:
                    mime = _text(row.get("mime_type")).lower()
                    file_name = _text(row.get("file_name"))
                    is_pdf = mime == "application/pdf" or file_name.lower().endswith(".pdf")
                    if not is_pdf:
                        continue
                    haystack = " ".join([_text(row.get("name")), file_name, mime]).lower()
                    if keyword_text and keyword_text not in haystack:
                        continue
                    name = _text(row.get("name") or file_name)
                    items.append({"id": int(row["id"]), "type": "pdf", "library": "attachment_library", "name": name, "title": name, "description": _text(file_name or mime), "mime_type": mime})
    return {"ok": True, "materials": items, "reason": "channel_welcome_materials_listed", "source": "ai_crm_next"}
