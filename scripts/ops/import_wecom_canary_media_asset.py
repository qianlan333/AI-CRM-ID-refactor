#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import struct
import sys
import zlib
from pathlib import Path
from typing import Any

try:
    from scripts.script_runtime import ensure_repo_root_on_path
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.script_runtime import ensure_repo_root_on_path

ensure_repo_root_on_path()

from aicrm_next.media_library.postgres_repo import PostgresMediaLibraryRepository  # noqa: E402
from aicrm_next.platform_foundation.execution_runtime.cutover import (  # noqa: E402
    RuntimeGenerationRepository,
)
from aicrm_next.platform_foundation.execution_runtime.repository import (  # noqa: E402
    normalize_runtime_database_url,
    open_runtime_connection,
)
from aicrm_next.shared.release import current_release_sha  # noqa: E402
from aicrm_next.shared.runtime import raw_database_url  # noqa: E402
from scripts.ops.configure_wecom_canary import load_canary_spec  # noqa: E402


AUTHORIZATION_ENV = "AICRM_WECOM_CANARY_MEDIA_IMPORT_AUTHORIZED"
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
MATERIAL_NAME = "AI-CRM ID validation canary image"
MATERIAL_FILE_NAME = "aicrm-id-validation-canary.png"
MATERIAL_TAG = "id-validation-canary"
MATERIAL_CATEGORY = "ID validation"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or verify one deterministic, local-only ID-validation image material on 49.",
    )
    parser.add_argument("--spec-file", required=True)
    parser.add_argument("--expected-release-sha", required=True)
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--expected-policy-version", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--apply", action="store_true", default=False)
    parser.add_argument("--confirmation", default="")
    return parser.parse_args(argv)


def _confirmation(generation: int) -> str:
    return f"IMPORT_WECOM_CANARY_MEDIA_{int(generation)}"


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = binascii.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def canary_png_bytes() -> bytes:
    width = 64
    height = 64
    pixel = bytes((38, 99, 235))
    scanlines = b"".join(b"\x00" + pixel * width for _ in range(height))
    return b"".join(
        (
            b"\x89PNG\r\n\x1a\n",
            _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            _png_chunk(b"IDAT", zlib.compress(scanlines, level=9)),
            _png_chunk(b"IEND", b""),
        )
    )


def _content_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require_image_canary_target(spec: dict[str, Any]) -> None:
    targets = tuple(spec.get("media_targets") or ())
    if len(targets) != 1:
        raise ValueError("media import requires exactly one canary media target")
    parts = str(targets[0] or "").split(":")
    if len(parts) != 3 or parts[0] != "image" or parts[2] != "image":
        raise ValueError("media import requires one image material uploaded as image")
    try:
        material_id = int(parts[1])
    except (TypeError, ValueError) as exc:
        raise ValueError("media import canary material id must be an integer") from exc
    if material_id <= 0:
        raise ValueError("media import canary material id must be positive")


def _runtime_ready(*, database_url: str, generation: int, policy_version: str) -> None:
    state = RuntimeGenerationRepository(database_url).read_state()
    if (
        state.active_generation != int(generation)
        or not state.claim_enabled
        or state.policy_version != str(policy_version)
        or state.external_claim_scope != "test_loopback"
    ):
        raise RuntimeError("media import requires the exact active test-loopback generation")
    with open_runtime_connection(database_url) as connection:
        running = connection.execute(
            "SELECT COUNT(*)::BIGINT AS count FROM queue_runtime_soak_run WHERE status = 'running'"
        ).fetchone()
    if int((running or {}).get("count") or 0):
        raise RuntimeError("media import is forbidden while a soak is running")


def _exact_existing(repository: PostgresMediaLibraryRepository) -> dict[str, Any] | None:
    listed = repository.list_items(
        "image",
        limit=100,
        offset=0,
        filters={"q": MATERIAL_NAME, "enabled_only": False},
    )
    matches = [item for item in list(listed.get("items") or []) if str(item.get("name") or "") == MATERIAL_NAME]
    if len(matches) > 1:
        raise RuntimeError("dedicated canary image name is not unique")
    if not matches:
        return None
    item_id = int(matches[0].get("id") or 0)
    if item_id <= 0:
        raise RuntimeError("dedicated canary image has an invalid id")
    return repository.get_item("image", str(item_id), include_data=True)


def _verify_item(item: dict[str, Any], *, expected_bytes: bytes) -> int:
    item_id = int(item.get("id") or 0)
    if item_id <= 0 or item.get("enabled") is not True:
        raise RuntimeError("dedicated canary image is unavailable")
    if str(item.get("mime_type") or "").split(";", 1)[0].strip().lower() != "image/png":
        raise RuntimeError("dedicated canary image has an unexpected media type")
    try:
        stored_bytes = base64.b64decode(str(item.get("data_base64") or ""), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RuntimeError("dedicated canary image source is invalid") from exc
    if _content_sha256(stored_bytes) != _content_sha256(expected_bytes):
        raise RuntimeError("dedicated canary image content does not match the deterministic source")
    return item_id


def _import(repository: PostgresMediaLibraryRepository) -> tuple[int, bool, str]:
    payload = canary_png_bytes()
    existing = _exact_existing(repository)
    created = existing is None
    if existing is None:
        encoded = base64.b64encode(payload).decode("ascii")
        existing = repository.save_item(
            "image",
            {
                "name": MATERIAL_NAME,
                "file_name": MATERIAL_FILE_NAME,
                "source": "id_validation_canary",
                "source_url": "",
                "data_base64": encoded,
                "mime_type": "image/png",
                "file_size": len(payload),
                "enabled": True,
                "description": "Dedicated harmless image for the 49-only ID validation canary.",
                "tags": [MATERIAL_TAG],
                "category": MATERIAL_CATEGORY,
                "ai_metadata": {
                    "id_validation_canary": True,
                    "content_sha256": _content_sha256(payload),
                },
            },
        )
    item_id = _verify_item(dict(existing or {}), expected_bytes=payload)
    return item_id, created, _content_sha256(payload)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    release_sha = str(args.expected_release_sha or "").strip()
    policy_version = str(args.expected_policy_version or "").strip()
    actor = str(args.actor or "").strip()
    reason = str(args.reason or "").strip()
    if FULL_SHA.fullmatch(release_sha) is None:
        raise ValueError("expected_release_sha must be one full SHA")
    if int(args.generation or 0) <= 0 or not policy_version or not actor or not reason:
        raise ValueError("generation, policy version, actor and reason are required")
    spec = load_canary_spec(args.spec_file)
    if "wecom.media.upload" not in set(spec["enabled_effect_types"]):
        raise ValueError("media import requires the enabled WeCom media effect")
    _require_image_canary_target(spec)

    plan = {
        "ok": True,
        "applied": False,
        "generation": int(args.generation),
        "policy_version": policy_version,
        "material_kind": "image",
        "upload_kind": "image",
        "deterministic_local_source": True,
        "target_values_redacted": True,
        "real_external_call_executed": False,
    }
    if not args.apply:
        print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
        return 0
    if str(os.getenv(AUTHORIZATION_ENV) or "").strip() != "1":
        raise RuntimeError(f"{AUTHORIZATION_ENV}=1 is required")
    if str(args.confirmation or "").strip() != _confirmation(int(args.generation)):
        raise RuntimeError(f"--confirmation must equal {_confirmation(int(args.generation))}")
    if current_release_sha() != release_sha:
        raise RuntimeError("active release SHA does not match the media import request")

    database_url = normalize_runtime_database_url(raw_database_url())
    _runtime_ready(
        database_url=database_url,
        generation=int(args.generation),
        policy_version=policy_version,
    )
    material_id, created, content_sha256 = _import(PostgresMediaLibraryRepository(database_url))
    print(
        json.dumps(
            {
                **plan,
                "applied": True,
                "created": created,
                "material_id": material_id,
                "content_sha256": content_sha256,
                "canary_spec_update_required": True,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
