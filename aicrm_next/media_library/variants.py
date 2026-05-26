from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from io import BytesIO
from typing import Any


VARIANT_KEYS = {"original", "thumb_160", "thumb_320", "preview_720"}


@dataclass(frozen=True)
class ImageVariant:
    image_id: int | str
    variant_key: str
    storage_backend: str
    storage_key: str
    public_url: str
    mime_type: str
    width: int
    height: int
    file_size: int
    checksum: str
    data_base64: str

    def metadata(self) -> dict[str, Any]:
        return {
            "image_id": self.image_id,
            "variant_key": self.variant_key,
            "storage_backend": self.storage_backend,
            "storage_key": self.storage_key,
            "public_url": self.public_url,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "file_size": self.file_size,
            "checksum": self.checksum,
        }


def variant_url(image_id: int | str, variant_key: str) -> str:
    return f"/api/admin/image-library/{image_id}/variants/{variant_key}"


def add_image_variant_urls(item: dict[str, Any], image_id: int | str | None = None) -> dict[str, Any]:
    target_id = image_id if image_id not in (None, "") else item.get("id")
    if target_id in (None, ""):
        return item
    item["thumb_160_url"] = variant_url(target_id, "thumb_160")
    item["thumb_320_url"] = variant_url(target_id, "thumb_320")
    item["thumb_url"] = item["thumb_320_url"]
    item["preview_url"] = variant_url(target_id, "preview_720")
    item["original_url"] = variant_url(target_id, "original")
    item.setdefault("width", 0)
    item.setdefault("height", 0)
    return item


def _checksum(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _mime_to_format(mime_type: str, *, has_alpha: bool = False) -> tuple[str, str]:
    try:
        from PIL import features

        if features.check("webp"):
            return "WEBP", "image/webp"
    except Exception:
        pass
    if has_alpha:
        return "PNG", "image/png"
    if mime_type in {"image/jpeg", "image/jpg"}:
        return "JPEG", "image/jpeg"
    return "PNG", "image/png"


def _encode_image(image: Any, source_mime_type: str) -> tuple[bytes, str]:
    has_alpha = image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in getattr(image, "info", {}))
    fmt, mime_type = _mime_to_format(source_mime_type, has_alpha=has_alpha)
    output = BytesIO()
    save_kwargs: dict[str, Any] = {}
    if fmt == "JPEG":
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        save_kwargs = {"quality": 82, "optimize": True}
    elif fmt == "WEBP":
        save_kwargs = {"quality": 82, "method": 4}
    image.save(output, fmt, **save_kwargs)
    return output.getvalue(), mime_type


def _fallback_variants(image_id: int | str, raw: bytes, mime_type: str, data_base64: str) -> dict[str, ImageVariant]:
    payload = data_base64 or base64.b64encode(raw).decode("ascii")
    size = len(raw)
    return {
        key: ImageVariant(
            image_id=image_id,
            variant_key=key,
            storage_backend="db_base64",
            storage_key=f"image_library/{image_id}/{key}",
            public_url="",
            mime_type=mime_type or "image/png",
            width=0,
            height=0,
            file_size=size,
            checksum=_checksum(raw),
            data_base64=payload,
        )
        for key in VARIANT_KEYS
    }


def generate_image_variants(*, image_id: int | str, data_base64: str, mime_type: str) -> dict[str, ImageVariant]:
    raw = base64.b64decode(data_base64 or "", validate=False)
    if not raw:
        raw = b""
    try:
        from PIL import Image, ImageOps

        source = Image.open(BytesIO(raw))
        source = ImageOps.exif_transpose(source)
        source_width, source_height = source.size
    except Exception:
        return _fallback_variants(image_id, raw, mime_type or "image/png", data_base64)

    variants: dict[str, ImageVariant] = {}

    def add_variant(key: str, image: Any, variant_mime: str | None = None, payload: bytes | None = None) -> None:
        payload_bytes = payload
        out_mime = variant_mime
        if payload_bytes is None:
            payload_bytes, out_mime = _encode_image(image, mime_type)
        width, height = image.size
        variants[key] = ImageVariant(
            image_id=image_id,
            variant_key=key,
            storage_backend="db_base64",
            storage_key=f"image_library/{image_id}/{key}",
            public_url="",
            mime_type=out_mime or mime_type or "image/png",
            width=int(width or 0),
            height=int(height or 0),
            file_size=len(payload_bytes),
            checksum=_checksum(payload_bytes),
            data_base64=base64.b64encode(payload_bytes).decode("ascii"),
        )

    add_variant("original", source, mime_type or "image/png", raw)

    for key, side in (("thumb_160", 160), ("thumb_320", 320)):
        if source_width <= side and source_height <= side:
            thumb = source.copy()
        else:
            thumb = ImageOps.fit(source, (side, side), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        add_variant(key, thumb)

    preview = source.copy()
    preview.thumbnail((720, 720), Image.Resampling.LANCZOS)
    add_variant("preview_720", preview)
    return variants


def variant_bytes(variant: dict[str, Any]) -> bytes:
    return base64.b64decode(str(variant.get("data_base64") or ""), validate=False)

