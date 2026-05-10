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
import json
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


def _to_jsonb_text(payload: Any, *, default: str) -> str:
    """把 dict/list/str 序列化成 JSON 文本，给 PG JSONB / SQLite TEXT 写入用。

    与 ``broadcast_jobs/repo.py:_to_jsonb_text`` 同源。``default`` 必须是有效
    JSON 字面量（``'[]'`` 或 ``'{}'``）。
    """
    if payload is None:
        return default
    if isinstance(payload, (dict, list)):
        return json.dumps(payload, ensure_ascii=False)
    if isinstance(payload, str):
        return payload or default
    return json.dumps(payload, ensure_ascii=False)


def _decode_jsonb(value: Any, *, default: Any) -> Any:
    """从 PG JSONB / SQLite TEXT 读出来的值统一解码。

    PG psycopg 已经把 JSONB 反序列化成 dict/list；SQLite 是字符串。两边都支持。
    """
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _normalize_tags(value: Any) -> list[str]:
    """把外部传入的 tags 标准化成去重 + 去空 + trim 的字符串数组。

    入参可能是 list / 逗号分隔字符串 / None。统一截断每个 tag 到 64 字符，
    最多保留 50 个，避免脏数据撑爆。
    """
    if value is None:
        return []
    if isinstance(value, str):
        # "好评,信任建立" → ["好评", "信任建立"]
        raw = [s.strip() for s in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw = [str(s).strip() for s in value]
    else:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for tag in raw:
        if not tag:
            continue
        clipped = tag[:64]
        if clipped in seen:
            continue
        seen.add(clipped)
        out.append(clipped)
        if len(out) >= 50:
            break
    return out


def _normalize_ai_metadata(value: Any) -> dict[str, Any]:
    """ai_metadata 必须是 dict；其他形态丢回空 dict 防写脏。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


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
        "description": str(row.get("description") or ""),
        "tags": _decode_jsonb(row.get("tags"), default=[]),
        "category": str(row.get("category") or ""),
        "ai_metadata": _decode_jsonb(row.get("ai_metadata"), default={}),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }
    if include_data:
        out["data_base64"] = str(row.get("data_base64") or "")
    return out


_LIST_COLUMNS = (
    "id, name, file_name, source, source_url, mime_type, file_size, "
    "thumb_media_id, thumb_media_id_expires_at, enabled, "
    "description, tags, category, ai_metadata, "
    "created_at, updated_at"
)


def list_images(
    *,
    enabled_only: bool = True,
    limit: int = 200,
    q: str | None = None,
    tags: list[str] | None = None,
    category: str | None = None,
    only_unlabeled: bool = False,
) -> list[dict[str, Any]]:
    """列出图片素材库记录，支持语义筛选。

    - ``q``：在 name + description 上做大小写不敏感的子串匹配
    - ``tags``：传 ``["好评", "信任"]``，命中任一即返回（OR 语义）
    - ``category``：精确匹配某一分类
    - ``only_unlabeled``：只返回 description / tags / category 任一为空的记录，
      给批量打标场景用
    """
    from ...db import get_db_backend

    is_pg = get_db_backend() == "postgres"
    db = get_db()
    cur = db.cursor()
    where: list[str] = []
    params: list[Any] = []

    if enabled_only:
        where.append("enabled")

    q_clean = (q or "").strip()
    if q_clean:
        like = f"%{q_clean}%"
        where.append("(name ILIKE ? OR description ILIKE ?)" if is_pg
                     else "(LOWER(name) LIKE LOWER(?) OR LOWER(description) LIKE LOWER(?))")
        params.extend([like, like])

    tag_filters = _normalize_tags(tags)
    if tag_filters:
        if is_pg:
            # 不用 JSONB 的 ``?|`` 操作符 —— cursor adapter 会把 ``?`` 翻译成
            # ``%s`` 占位符，跟它撞车。改用 jsonb_array_elements_text 展开后
            # ``= ANY(?)``，psycopg 会把 list 适配成 text[]。
            where.append(
                "EXISTS (SELECT 1 FROM jsonb_array_elements_text(tags) AS tt "
                "WHERE tt = ANY(?))"
            )
            params.append(tag_filters)
        else:
            # SQLite: tags 是 JSON 字符串，对每个 tag 用 LIKE 匹配带引号的文本
            sub: list[str] = []
            for t in tag_filters:
                sub.append("tags LIKE ?")
                # JSON 数组里 tag 值带双引号，不会跟 description 混
                params.append(f'%"{t}"%')
            where.append("(" + " OR ".join(sub) + ")")

    cat_clean = (category or "").strip()
    if cat_clean:
        where.append("category = ?")
        params.append(cat_clean)

    if only_unlabeled:
        if is_pg:
            where.append(
                "(description = '' OR category = '' "
                "OR jsonb_array_length(tags) = 0)"
            )
        else:
            # SQLite: tags 是 TEXT，'[]' 表示空数组
            where.append(
                "(description = '' OR category = '' "
                "OR tags = '' OR tags = '[]')"
            )

    sql = f"SELECT {_LIST_COLUMNS} FROM image_library"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
    params.append(int(limit))

    cur.execute(sql, tuple(params))
    return [_serialize(_row_to_dict(row)) for row in cur.fetchall() or []]


def list_categories_and_tags(*, enabled_only: bool = True) -> dict[str, list[str]]:
    """聚合当前已用的 category 和 tag 池，给前端筛选 / Skill 选项发现用。

    PG 上能下推 distinct + jsonb_array_elements_text，但实现要 backend 分支；
    考虑数据规模在万级以下，统一在 Python 端聚合即可，简单不易错。
    """
    db = get_db()
    cur = db.cursor()
    sql = "SELECT category, tags FROM image_library"
    if enabled_only:
        sql += " WHERE enabled"
    cur.execute(sql)
    rows = cur.fetchall() or []
    cats: set[str] = set()
    tag_set: set[str] = set()
    for row in rows:
        record = _row_to_dict(row)
        c = str(record.get("category") or "").strip()
        if c:
            cats.add(c)
        for tag in _decode_jsonb(record.get("tags"), default=[]):
            t = str(tag or "").strip()
            if t:
                tag_set.add(t)
    return {
        "categories": sorted(cats),
        "tags": sorted(tag_set),
    }


def get_image(image_id: int, *, include_data: bool = False) -> dict[str, Any]:
    if not image_id:
        return {}
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM image_library WHERE id = ?", (int(image_id),))
    row = cur.fetchone()
    return _serialize(_row_to_dict(row), include_data=include_data) if row else {}


def _insert_image(
    *,
    name: str,
    file_name: str,
    source: str,
    source_url: str,
    data_base64: str,
    mime_type: str,
    file_size: int,
    description: str = "",
    tags: Any = None,
    category: str = "",
    ai_metadata: Any = None,
) -> int:
    if source not in _VALID_SOURCES:
        raise ValueError(f"invalid source: {source}")
    from ...db import get_db_backend

    is_pg = get_db_backend() == "postgres"
    db = get_db()
    cur = db.cursor()
    # PG: thumb_media_id_expires_at 是 TIMESTAMPTZ nullable，写入 '' 抛 InvalidDatetimeFormat
    # 必须用 NULL；SQLite: 是 TEXT NOT NULL DEFAULT ''，沿用空字符串
    expires_placeholder = None if is_pg else ""
    tags_norm = _normalize_tags(tags)
    metadata_norm = _normalize_ai_metadata(ai_metadata)
    # PG JSONB 和 SQLite TEXT 都接受 JSON 字符串（psycopg3 隐式 cast text→jsonb）。
    # 与 broadcast_jobs/repo.py 同套范式。
    tags_payload = _to_jsonb_text(tags_norm, default="[]")
    ai_meta_payload = _to_jsonb_text(metadata_norm, default="{}")
    cur.execute(
        """
        INSERT INTO image_library
            (name, file_name, source, source_url, data_base64, mime_type, file_size,
             thumb_media_id, thumb_media_id_expires_at, enabled,
             description, tags, category, ai_metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?)
        """,
        (
            (name or "").strip()[:200],
            (file_name or "").strip()[:200] or _DEFAULT_FILENAME,
            source,
            (source_url or "").strip()[:1000],
            data_base64 or "",
            (mime_type or "image/png").strip()[:80],
            int(file_size or 0),
            expires_placeholder,
            True if is_pg else 1,  # enabled: PG BOOLEAN / SQLite INTEGER
            (description or "").strip()[:4000],
            tags_payload,
            (category or "").strip()[:80],
            ai_meta_payload,
        ),
    )
    db.commit()
    return int(cur.lastrowid or 0)


def create_image_from_upload(
    *,
    file_bytes: bytes,
    file_name: str,
    mime_type: str,
    name: str = "",
    description: str = "",
    tags: Any = None,
    category: str = "",
    ai_metadata: Any = None,
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
        description=description,
        tags=tags,
        category=category,
        ai_metadata=ai_metadata,
    )
    return get_image(image_id)


def create_image_from_url(
    *,
    url: str,
    name: str = "",
    mime_type: str = "image/png",
    description: str = "",
    tags: Any = None,
    category: str = "",
    ai_metadata: Any = None,
) -> dict[str, Any]:
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
        description=description,
        tags=tags,
        category=category,
        ai_metadata=ai_metadata,
    )
    return get_image(image_id)


def create_image_from_base64(
    *,
    data_base64: str,
    file_name: str = "",
    mime_type: str = "image/png",
    name: str = "",
    description: str = "",
    tags: Any = None,
    category: str = "",
    ai_metadata: Any = None,
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
        description=description,
        tags=tags,
        category=category,
        ai_metadata=ai_metadata,
    )
    return get_image(image_id)


def update_image(
    image_id: int,
    *,
    name: str | None = None,
    enabled: bool | None = None,
    description: str | None = None,
    tags: Any = None,
    category: str | None = None,
    ai_metadata: Any = None,
) -> dict[str, Any]:
    """更新元数据。``tags`` / ``ai_metadata`` 传 ``None`` 表示不改；要清空请传 ``[]`` / ``{}``。"""
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
        params.append(bool(enabled))  # PG BOOLEAN / SQLite truthy
    if description is not None:
        sets.append("description = ?")
        params.append(str(description).strip()[:4000])
    if tags is not None:
        sets.append("tags = ?")
        params.append(_to_jsonb_text(_normalize_tags(tags), default="[]"))
    if category is not None:
        sets.append("category = ?")
        params.append(str(category).strip()[:80])
    if ai_metadata is not None:
        sets.append("ai_metadata = ?")
        params.append(_to_jsonb_text(_normalize_ai_metadata(ai_metadata), default="{}"))
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
        (False, int(image_id)),  # PG BOOLEAN / SQLite truthy
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
    "list_categories_and_tags",
    "get_image",
    "create_image_from_upload",
    "create_image_from_url",
    "create_image_from_base64",
    "update_image",
    "delete_image",
    "resolve_image_media_id",
]
