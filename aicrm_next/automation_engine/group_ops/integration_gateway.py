from __future__ import annotations

from typing import Any

from aicrm_next.shared.errors import ContractError

from .domain import clean_text


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
    attachments: list[dict[str, Any]] = []
    image_media_ids: list[str] = []
    for image_id in _int_ids(content_package.get("image_library_ids"), limit=3):
        try:
            from wecom_ability_service.domains import image_library

            media_id = clean_text(image_library.resolve_image_media_id(image_id))
        except Exception as exc:
            raise ContractError(f"image_library_resolve_failed:id={image_id}:{exc}") from exc
        if not media_id:
            raise ContractError(f"image_library_resolve_failed:id={image_id}:empty_media_id")
        image_media_ids.append(media_id)
    for miniprogram_id in _int_ids(content_package.get("miniprogram_library_ids"), limit=1):
        try:
            from wecom_ability_service.domains import miniprogram_library

            attachments.append(miniprogram_library.materialize_miniprogram_attachment(miniprogram_id))
        except Exception as exc:
            raise ContractError(f"miniprogram_resolve_failed:id={miniprogram_id}:{exc}") from exc
    for attachment_id in _int_ids(content_package.get("attachment_library_ids"), limit=9):
        try:
            from wecom_ability_service.domains import attachment_library

            attachments.append(attachment_library.materialize_file_attachment(attachment_id))
        except Exception as exc:
            raise ContractError(f"attachment_resolve_failed:id={attachment_id}:{exc}") from exc
    return attachments, image_media_ids
