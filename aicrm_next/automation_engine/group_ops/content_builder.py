from __future__ import annotations

from copy import deepcopy
from typing import Any

from aicrm_next.media_library.repo import MediaLibraryRepository, build_media_library_repository
from aicrm_next.send_content.application import NormalizeSendContentPackageCommand
from aicrm_next.shared.errors import ContractError

MAX_PRIVATE_MESSAGE_IMAGES = 3
MAX_PRIVATE_MESSAGE_ATTACHMENTS = 9
SUPPORTED_PRIVATE_MESSAGE_ATTACHMENT_TYPES = {"file", "image", "miniprogram"}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _normalize_sender(value: Any) -> str:
    if isinstance(value, list):
        for item in value:
            sender = _clean_text(item)
            if sender:
                return sender
        return ""
    return _clean_text(value)


def _assert_media_id(media_id: str, *, label: str) -> str:
    value = _clean_text(media_id)
    if not value:
        raise ContractError(f"{label} must include media_id")
    if any(ch.isspace() for ch in value):
        raise ContractError(f"{label} media_id is invalid")
    return value


def _first_text(*values: Any) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("metadata") if isinstance(item.get("metadata"), dict) else {}


class MessageAttachmentNormalizer:
    def normalize(self, attachments: list[Any]) -> tuple[list[dict[str, Any]], int]:
        normalized: list[dict[str, Any]] = []
        image_count = 0
        for item in attachments or []:
            attachment = self._normalize_one(item)
            normalized.append(attachment)
            if attachment.get("msgtype") == "image":
                image_count += 1
        if image_count > MAX_PRIVATE_MESSAGE_IMAGES:
            raise ContractError(f"at most {MAX_PRIVATE_MESSAGE_IMAGES} images are allowed")
        if len(normalized) > MAX_PRIVATE_MESSAGE_ATTACHMENTS:
            raise ContractError(f"at most {MAX_PRIVATE_MESSAGE_ATTACHMENTS} attachments are allowed")
        return normalized, image_count

    def _normalize_one(self, item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ContractError("attachments entries must be objects")
        raw = deepcopy(item)
        msgtype = _clean_text(raw.get("msgtype")).lower()
        if not msgtype:
            raise ContractError("attachments entries must include msgtype")
        if msgtype not in SUPPORTED_PRIVATE_MESSAGE_ATTACHMENT_TYPES:
            raise ContractError("attachments msgtype is not supported")
        payload = raw.get(msgtype)
        if not isinstance(payload, dict) or not payload:
            raise ContractError(f"attachments entries must include a non-empty '{msgtype}' object")
        if msgtype == "image":
            return {"msgtype": "image", "image": {"media_id": _assert_media_id(payload.get("media_id"), label="image attachments")}}
        if msgtype == "file":
            file_payload = deepcopy(payload)
            file_payload["media_id"] = _assert_media_id(file_payload.get("media_id"), label="file attachments")
            return {"msgtype": "file", "file": file_payload}
        return {"msgtype": "miniprogram", "miniprogram": self._normalize_miniprogram(payload)}

    def _normalize_miniprogram(self, payload: dict[str, Any]) -> dict[str, str]:
        appid = _clean_text(payload.get("appid") or payload.get("app_id"))
        page = _clean_text(payload.get("page") or payload.get("pagepath") or payload.get("page_path"))
        title = _clean_text(payload.get("title"))
        raw_pic_media_id = payload.get("pic_media_id") or payload.get("thumb_media_id")
        if not _clean_text(raw_pic_media_id):
            raise ContractError("miniprogram attachments must include pic_media_id")
        pic_media_id = _assert_media_id(raw_pic_media_id, label="miniprogram attachments")
        if not appid:
            raise ContractError("miniprogram attachments must include appid")
        if not page:
            raise ContractError("miniprogram attachments must include page")
        if not title:
            raise ContractError("miniprogram attachments must include title")
        return {"appid": appid, "page": page, "title": title, "pic_media_id": pic_media_id}


class SendContentPackageResolver:
    def __init__(self, media_repo: MediaLibraryRepository | None = None) -> None:
        self._media_repo = media_repo

    def resolve(self, content_package: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[str]]:
        normalized = NormalizeSendContentPackageCommand()(content_package or {}, text_enabled=True, require_body=False)
        attachments: list[dict[str, Any]] = []
        image_media_ids: list[str] = []
        for image_id in normalized.get("image_library_ids") or []:
            item = self._get_item("image", image_id)
            media_id = _first_text(item.get("thumb_media_id"), item.get("wecom_media_id"), item.get("media_id"), _metadata(item).get("media_id"))
            if not media_id:
                raise ContractError(f"image_library_resolve_failed:id={image_id}:media_id_required")
            image_media_ids.append(_assert_media_id(media_id, label="image library"))
        for miniprogram_id in normalized.get("miniprogram_library_ids") or []:
            item = self._get_item("miniprogram", miniprogram_id)
            metadata = _metadata(item)
            thumb_media_id = _first_text(item.get("thumb_media_id"), item.get("pic_media_id"), metadata.get("thumb_media_id"), metadata.get("pic_media_id"))
            attachments.append(
                {
                    "msgtype": "miniprogram",
                    "miniprogram": {
                        "appid": _first_text(item.get("appid"), metadata.get("appid")),
                        "page": _first_text(item.get("page"), item.get("pagepath"), item.get("page_path"), metadata.get("pagepath"), metadata.get("page_path")),
                        "title": _first_text(item.get("title"), item.get("name"), metadata.get("title")),
                        "pic_media_id": thumb_media_id,
                    },
                }
            )
        for attachment_id in normalized.get("attachment_library_ids") or []:
            item = self._get_item("attachment", attachment_id)
            metadata = _metadata(item)
            media_id = _first_text(item.get("media_id"), item.get("wecom_media_id"), metadata.get("media_id"), metadata.get("wecom_media_id"))
            attachments.append({"msgtype": "file", "file": {"media_id": media_id}})
        return attachments, image_media_ids

    def _get_item(self, kind: str, item_id: int) -> dict[str, Any]:
        repo = self._repo()
        item = repo.get_item(kind, str(item_id), include_data=False)
        if not item:
            raise ContractError(f"{kind}_library_resolve_failed:id={item_id}:not_found")
        if item.get("enabled") is False:
            raise ContractError(f"{kind}_library_resolve_failed:id={item_id}:disabled")
        return item

    def _repo(self) -> MediaLibraryRepository:
        if self._media_repo is None:
            self._media_repo = build_media_library_repository()
        return self._media_repo


class PrivateMessagePayloadBuilder:
    def __init__(self, *, attachment_normalizer: MessageAttachmentNormalizer | None = None) -> None:
        self._attachment_normalizer = attachment_normalizer or MessageAttachmentNormalizer()

    def build_request_payload(self, payload: dict[str, Any], *, allow_empty_draft: bool = False) -> tuple[dict[str, Any], int]:
        normalized_payload = deepcopy(payload or {})
        text = self._extract_text(normalized_payload)
        attachments = list(_normalize_items(normalized_payload.get("attachments")))
        for media_id in _normalize_items(normalized_payload.get("image_media_ids")):
            clean_media_id = _assert_media_id(media_id, label="image media")
            attachments.append({"msgtype": "image", "image": {"media_id": clean_media_id}})
        normalized_attachments, image_count = self._attachment_normalizer.normalize(attachments)
        if image_count > MAX_PRIVATE_MESSAGE_IMAGES:
            raise ContractError(f"at most {MAX_PRIVATE_MESSAGE_IMAGES} images are allowed")
        if len(normalized_attachments) > MAX_PRIVATE_MESSAGE_ATTACHMENTS:
            raise ContractError(f"at most {MAX_PRIVATE_MESSAGE_ATTACHMENTS} attachments are allowed")

        result: dict[str, Any] = {}
        sender = _normalize_sender(normalized_payload.get("sender"))
        if sender:
            result["sender"] = sender
        if text:
            result["text"] = {"content": text}
        if normalized_attachments:
            result["attachments"] = normalized_attachments
        if not result.get("text") and not result.get("attachments"):
            if allow_empty_draft:
                return result, 0
            raise ContractError("content.text or content.attachments is required")
        return result, image_count

    def build(self, payload: dict[str, Any], *, allow_empty_draft: bool = False) -> dict[str, Any]:
        normalized, _image_count = self.build_request_payload(payload, allow_empty_draft=allow_empty_draft)
        return normalized

    def _extract_text(self, payload: dict[str, Any]) -> str:
        text_payload = payload.get("text")
        if isinstance(text_payload, dict):
            return _clean_text(text_payload.get("content"))
        return _clean_text(payload.get("content"))
