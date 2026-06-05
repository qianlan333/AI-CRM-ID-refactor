from __future__ import annotations

from typing import Any

from .domain import clean_text
from .content_builder import SendContentPackageResolver


def _int_ids(values: Any, *, limit: int = 9) -> list[int]:
    result: list[int] = []
    for value in list(values or []):
        try:
            item = int(value or 0)
        except (TypeError, ValueError):
            continue
        if item > 0 and item not in result:
            result.append(item)
    return result[:limit]


def resolve_group_ops_content_package_materials(content_package: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    normalized = {
        "content_text": clean_text(content_package.get("content_text") if isinstance(content_package, dict) else ""),
        "image_library_ids": _int_ids(content_package.get("image_library_ids") if isinstance(content_package, dict) else [], limit=3),
        "miniprogram_library_ids": _int_ids(content_package.get("miniprogram_library_ids") if isinstance(content_package, dict) else [], limit=1),
        "attachment_library_ids": _int_ids(content_package.get("attachment_library_ids") if isinstance(content_package, dict) else [], limit=9),
    }
    if not any(
        normalized[key]
        for key in ("image_library_ids", "miniprogram_library_ids", "attachment_library_ids")
    ):
        return [], []
    return SendContentPackageResolver().resolve(normalized)
