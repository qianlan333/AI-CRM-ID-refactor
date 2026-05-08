"""租户级图片素材库

集中管理所有可被复用的图片：小程序卡片缩略图、campaign 群发配图、自动化欢迎语
配图、SOP 配图等。每条记录持有原图（base64 / 外链 URL），发送前调
``resolve_image_media_id`` 上传到企微换出 ``media_id``，并把结果缓存 2 天
（企微临时素材有效期 3 天，留 1 天 buffer 自动重传）—— 与 miniprogram_library
完全相同的机制，避免每次群发都重复上传。

核心 API：
- ``list_images`` / ``get_image`` / ``create_image`` / ``update_image`` / ``delete_image``
- ``create_image_from_upload(file_bytes, file_name, mime_type, name='')``
- ``create_image_from_url(url, name='')``
- ``create_image_from_base64(data_base64, file_name, mime_type, name='')``
- ``resolve_image_media_id(image_id)`` —— 发送前调用，返回有效 media_id
"""
from __future__ import annotations

import base64
import logging
import mimetypes
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from ...db import get_db
from ...wecom_client import WeComClient

_logger = logging.getLogger(__name__)

THUMB_MEDIA_TTL_DAYS = 2
_DEFAULT_FILENAME = "image-library-asset.png"
_VALID_SOURCES = {"upload", "url", "base64"}


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    return dict(row)


def _serialize(row: dict[str, Any], *, include_data: bool = False) -> dict[str, Any]:
    """默认不返回 data_base64（可能很大），列表场景下避免拉爆 payload。"""
    if not row:
        return {}
    enabled_raw = row.get("enabled")
    if isinstance(enabled_raw, bool):
        enabled = enabled_raw
    else:
        try:
            enabled = bool(int(enabled_raw or 0))
        except (TypeError, ValueError):
            enabled = bool(enabled_raw)
    out = {
        "id": int(row.get("id") or 0),
        "name": str(row.get("name") or ""),
        "file_name": str(row.get("file_name") or ""),
        "source": str(row.get("source") or "upload"),
        "source_url": str(row.get("source_url") or ""),
        "mime_type": str(row.get("mime_type") or "image/png"),
        "file_size": int(row.get("file_size") or 0),
        "thumb_media_id": str(row.get("thumb_media_id") or ""),
        "thumb_media_id_expires_at": str(row.get("thumb_media_id_expires_at") or ""),
        "enabled": enabled,
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }
    if include_data:
        out["data_base64"] = str(row.get("data_base64") or "")
    return out


def list_images(*, enabled_only: bool = True, limit: int = 200) -> list[dict[str, Any]]:
    db = get_db()
    cur = db.cursor()
    if enabled_only:
        cur.execute(
            "SELECT id, name, file_name, source, source_url, mime_type, file_size, "
            "thumb_media_id, thumb_media_id_expires_at, enabled, created_at, updated_at "
            "FROM image_library WHERE enabled IN (1, TRUE) "
            "ORDER BY updated_at DESC, id DESC LIMIT ?",
            (int(limit),),
        )
    else:
        cur.execute(
            "SELECT id, name, file_name, source, source_url, mime_type, file_size, "
            "thumb_media_id, thumb_media_id_expires_at, enabled, created_at, updated_at "
            "FROM image_library ORDER BY updated_at DESC, id DESC LIMIT ?",
            (int(limit),),
        )
    return [_serialize(_row_to_dict(row)) for row in cur.fetchall() or []]


def get_image(image_id: int, *, include_data: bool = False) -> dict[str, Any]:
    if not image_id:
        return {}
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM image_library WHERE id = ?", (int(image_id),))
    row = cur.fetchone()
    return _serialize(_row_to_dict(row), include_data=include_data) if row else {}


def _insert_image(*, name: str, file_name: str, source: str, source_url: str,
                  data_base64: str, mime_type: str, file_size: int) -> int:
    if source not in _VALID_SOURCES:
        raise ValueError(f"invalid source: {source}")
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO image_library
            (name, file_name, source, source_url, data_base64, mime_type, file_size,
             thumb_media_id, thumb_media_id_expires_at, enabled)
        VALUES (?, ?, ?, ?, ?, ?, ?, '', '', ?)
        """,
        (
            (name or "").strip()[:200],
            (file_name or "").strip()[:200] or _DEFAULT_FILENAME,
            source,
            (source_url or "").strip()[:1000],
            data_base64 or "",
            (mime_type or "image/png").strip()[:80],
            int(file_size or 0),
            1,
        ),
    )
    db.commit()
    return int(cur.lastrowid or 0)


def create_image_from_upload(
    *, file_bytes: bytes, file_name: str, mime_type: str, name: str = ""
) -> dict[str, Any]:
    if not file_bytes:
        raise ValueError("file_bytes is empty")
    if not (mime_type or "").startswith("image/"):
        raise ValueError(f"only image/* allowed, got {mime_type}")
    if len(file_bytes) > 5 * 1024 * 1024:
        raise ValueError("file too large (max 5MB)")
    encoded = base64.b64encode(file_bytes).decode("ascii")
    image_id = _insert_image(
        name=name or file_name,
        file_name=file_name,
        source="upload",
        source_url="",
        data_base64=encoded,
        mime_type=mime_type,
        file_size=len(file_bytes),
    )
    return get_image(image_id)


def create_image_from_url(*, url: str, name: str = "", mime_type: str = "image/png") -> dict[str, Any]:
    url = (url or "").strip()
    if not url:
        raise ValueError("url is empty")
    image_id = _insert_image(
        name=name or url.rsplit("/", 1)[-1],
        file_name=url.rsplit("/", 1)[-1].split("?", 1)[0],
        source="url",
        source_url=url,
        data_base64="",
        mime_type=mime_type,
        file_size=0,
    )
    return get_image(image_id)


def create_image_from_base64(
    *, data_base64: str, file_name: str = "", mime_type: str = "image/png", name: str = ""
) -> dict[str, Any]:
    payload = (data_base64 or "").strip()
    if not payload:
        raise ValueError("data_base64 is empty")
    if payload.startswith("data:"):
        # data:image/png;base64,xxx → 拆掉 data url 头，记录正确 mime_type
        header, _, body = payload.partition(",")
        if not body:
            raise ValueError("invalid data url")
        if header.startswith("data:") and ";" in header:
            mime_type = header[5:].split(";", 1)[0] or mime_type
        payload = body
    try:
        decoded = base64.b64decode(payload)
    except (ValueError, TypeError) as exc:
        raise ValueError("data_base64 decode failed") from exc
    if len(decoded) > 5 * 1024 * 1024:
        raise ValueError("file too large (max 5MB)")
    image_id = _insert_image(
        name=name or (file_name or _DEFAULT_FILENAME),
        file_name=file_name,
        source="base64",
        source_url="",
        data_base64=payload,
        mime_type=mime_type,
        file_size=len(decoded),
    )
    return get_image(image_id)


def update_image(image_id: int, *, name: str | None = None, enabled: bool | None = None) -> dict[str, Any]:
    existing = get_image(image_id)
    if not existing:
        raise ValueError(f"image_library id={image_id} not found")
    sets: list[str] = []
    params: list[Any] = []
    if name is not None:
        sets.append("name = ?")
        params.append(str(name).strip()[:200])
    if enabled is not None:
        sets.append("enabled = ?")
        params.append(1 if bool(enabled) else 0)
    if not sets:
        return existing
    sets.append("updated_at = CURRENT_TIMESTAMP")
    params.append(int(image_id))
    db = get_db()
    cur = db.cursor()
    cur.execute(f"UPDATE image_library SET {', '.join(sets)} WHERE id = ?", tuple(params))
    db.commit()
    return get_image(image_id)


def delete_image(image_id: int) -> bool:
    """软删（enabled=false）。已被 miniprogram_library / campaign_steps 引用的不实删，避免悬空。"""
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE image_library SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (0, int(image_id)),
    )
    db.commit()
    return (cur.rowcount or 0) > 0


def _decode_image_bytes(record_full: dict[str, Any]) -> tuple[bytes, str, str]:
    """从图片记录里取原始字节 + content-type + 文件名。

    record_full 必须 include data_base64（即 ``get_image(id, include_data=True)`` 的返回）。
    """
    source = record_full.get("source") or "upload"
    file_name = record_full.get("file_name") or _DEFAULT_FILENAME
    mime_type = record_full.get("mime_type") or "image/png"

    if source in ("upload", "base64"):
        encoded = record_full.get("data_base64") or ""
        if not encoded:
            raise ValueError(f"image {record_full.get('id')} 没有 base64 数据")
        if encoded.startswith("data:"):
            _, _, body = encoded.partition(",")
            encoded = body or encoded
        try:
            return base64.b64decode(encoded), mime_type, file_name
        except (ValueError, TypeError) as exc:
            raise ValueError(f"image {record_full.get('id')} base64 解码失败") from exc

    if source == "url":
        url = (record_full.get("source_url") or "").strip()
        if not url:
            raise ValueError(f"image {record_full.get('id')} source=url 但 source_url 为空")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        ct = response.headers.get("Content-Type", mime_type).split(";", 1)[0].strip() or mime_type
        if not file_name or "." not in file_name:
            ext = mimetypes.guess_extension(ct) or ".png"
            file_name = (url.rsplit("/", 1)[-1].split("?", 1)[0] or _DEFAULT_FILENAME).split(".", 1)[0] + ext
        return response.content, ct, file_name

    raise ValueError(f"unsupported source: {source}")


def _persist_media_id(image_id: int, media_id: str, expires_at: datetime) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        UPDATE image_library
        SET thumb_media_id = ?, thumb_media_id_expires_at = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (media_id, _iso(expires_at), int(image_id)),
    )
    db.commit()


def resolve_image_media_id(
    image_id: int,
    *,
    upload_image: Any | None = None,
    now: datetime | None = None,
) -> str:
    """返回图片的有效企微 media_id；过期或未上传则重新上传。

    与 ``miniprogram_library.resolve_thumb_media_id`` 同套机制。``upload_image``
    可在测试里注入。
    """
    record = get_image(image_id, include_data=True)
    if not record:
        raise ValueError(f"image_library id={image_id} not found")
    if not record.get("enabled", False):
        raise ValueError(f"image_library id={image_id} is disabled")

    now_dt = now or _now_utc()
    cached_media_id = record.get("thumb_media_id") or ""
    expires_at = _parse_iso(record.get("thumb_media_id_expires_at"))
    if cached_media_id and expires_at and expires_at > now_dt:
        return cached_media_id

    file_bytes, content_type, file_name = _decode_image_bytes(record)
    if upload_image is None:
        client = WeComClient.from_app()
        upload_image = client._upload_private_message_image
    media_id = upload_image(file_name, file_bytes, content_type)
    new_expires = now_dt + timedelta(days=THUMB_MEDIA_TTL_DAYS)
    _persist_media_id(int(record["id"]), media_id, new_expires)
    return media_id


__all__ = [
    "list_images",
    "get_image",
    "create_image_from_upload",
    "create_image_from_url",
    "create_image_from_base64",
    "update_image",
    "delete_image",
    "resolve_image_media_id",
]
