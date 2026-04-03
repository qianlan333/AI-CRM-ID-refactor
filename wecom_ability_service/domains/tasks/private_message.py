from __future__ import annotations

import base64
import mimetypes
from copy import deepcopy
from typing import Any, Callable

MAX_PRIVATE_MESSAGE_IMAGES = 9


def _normalize_str(value: Any) -> str:
    return str(value or "")


def extract_private_message_text(payload: dict[str, Any]) -> str:
    text_payload = payload.get("text")
    if isinstance(text_payload, dict):
        return _normalize_str(text_payload.get("content"))
    return _normalize_str(payload.get("content"))


def _normalize_image_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _normalize_binary_image_spec(item: Any, index: int) -> dict[str, Any]:
    if isinstance(item, str):
        raw = item.strip()
        if raw.startswith("data:"):
            return {
                "data_url": raw,
                "file_name": f"image-{index}.png",
                "content_type": "image/png",
            }
        return {
            "data_base64": raw,
            "file_name": f"image-{index}.png",
            "content_type": "image/png",
        }

    if not isinstance(item, dict):
        raise ValueError("images entries must be strings or objects")

    file_name = str(item.get("file_name") or item.get("name") or f"image-{index}.png").strip() or f"image-{index}.png"
    content_type = str(item.get("content_type") or item.get("mime_type") or "").strip()
    media_id = str(item.get("media_id") or "").strip()
    if media_id:
        return {
            "media_id": media_id,
            "file_name": file_name,
            "content_type": content_type or mimetypes.guess_type(file_name)[0] or "image/png",
        }

    data_url = str(item.get("data_url") or "").strip()
    if data_url:
        return {
            "data_url": data_url,
            "file_name": file_name,
            "content_type": content_type or mimetypes.guess_type(file_name)[0] or "image/png",
        }

    data_base64 = str(item.get("data_base64") or item.get("base64") or "").strip()
    if data_base64:
        return {
            "data_base64": data_base64,
            "file_name": file_name,
            "content_type": content_type or mimetypes.guess_type(file_name)[0] or "image/png",
        }

    raise ValueError("images entries must include media_id, data_url, or data_base64")


def _decode_data_url(data_url: str) -> tuple[bytes, str]:
    header, _, encoded = data_url.partition(",")
    if not encoded:
        raise ValueError("invalid image data_url")
    content_type = "image/png"
    if header.startswith("data:") and ";base64" in header:
        content_type = header[5:].split(";", 1)[0] or content_type
    try:
        return base64.b64decode(encoded), content_type
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid image data_url") from exc


def _decode_base64(data_base64: str) -> bytes:
    try:
        return base64.b64decode(data_base64)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid image data_base64") from exc


def normalize_private_message_images(payload: dict[str, Any]) -> list[dict[str, Any]]:
    images = []

    for index, item in enumerate(_normalize_image_list(payload.get("image_media_ids")), start=1):
        media_id = str(item or "").strip()
        if not media_id:
            continue
        images.append({"media_id": media_id, "file_name": f"image-{index}.png", "content_type": "image/png"})

    image_offset = len(images)
    for index, item in enumerate(_normalize_image_list(payload.get("images")), start=image_offset + 1):
        images.append(_normalize_binary_image_spec(item, index))

    if len(images) > MAX_PRIVATE_MESSAGE_IMAGES:
        raise ValueError(f"at most {MAX_PRIVATE_MESSAGE_IMAGES} images are allowed")
    return images


def count_private_message_images(payload: dict[str, Any]) -> int:
    image_count = len(normalize_private_message_images(payload))
    for attachment in _normalize_image_list(payload.get("attachments")):
        if not isinstance(attachment, dict):
            continue
        if str(attachment.get("msgtype") or "").strip().lower() == "image":
            image_count += 1
    if image_count > MAX_PRIVATE_MESSAGE_IMAGES:
        raise ValueError(f"at most {MAX_PRIVATE_MESSAGE_IMAGES} images are allowed")
    return image_count


def has_private_message_body(payload: dict[str, Any]) -> bool:
    return bool(extract_private_message_text(payload).strip() or count_private_message_images(payload))


def build_private_message_request_payload(
    payload: dict[str, Any],
    *,
    upload_image: Callable[[str, bytes, str], str] | None = None,
) -> tuple[dict[str, Any], int]:
    normalized_payload = deepcopy(payload)
    content = extract_private_message_text(normalized_payload)
    attachments = [deepcopy(item) for item in _normalize_image_list(normalized_payload.get("attachments")) if isinstance(item, dict)]

    image_specs = normalize_private_message_images(normalized_payload)
    image_count = 0
    for attachment in attachments:
        if str(attachment.get("msgtype") or "").strip().lower() == "image":
            image_count += 1

    for spec in image_specs:
        media_id = str(spec.get("media_id") or "").strip()
        if not media_id:
            if upload_image is None:
                raise ValueError("image upload is not configured")
            content_type = str(spec.get("content_type") or "").strip() or mimetypes.guess_type(spec["file_name"])[0] or "image/png"
            if spec.get("data_url"):
                file_bytes, content_type_from_url = _decode_data_url(str(spec["data_url"]))
                if not spec.get("content_type"):
                    content_type = content_type_from_url
            else:
                file_bytes = _decode_base64(str(spec.get("data_base64") or ""))
            media_id = upload_image(str(spec.get("file_name") or "image.png"), file_bytes, content_type)
        attachments.append({"msgtype": "image", "image": {"media_id": media_id}})
        image_count += 1

    if image_count > MAX_PRIVATE_MESSAGE_IMAGES:
        raise ValueError(f"at most {MAX_PRIVATE_MESSAGE_IMAGES} images are allowed")

    normalized_payload.pop("images", None)
    normalized_payload.pop("image_media_ids", None)
    normalized_payload.pop("content", None)

    if content.strip():
        normalized_payload["text"] = {"content": content}
    else:
        normalized_payload.pop("text", None)

    if attachments:
        normalized_payload["attachments"] = attachments
    else:
        normalized_payload.pop("attachments", None)

    if not normalized_payload.get("text") and not normalized_payload.get("attachments"):
        raise ValueError("content or images is required")

    return normalized_payload, image_count
