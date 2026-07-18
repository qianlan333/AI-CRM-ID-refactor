#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from scripts.script_runtime import ensure_repo_root_on_path
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.script_runtime import ensure_repo_root_on_path

ensure_repo_root_on_path()

from aicrm_next.automation_engine import channels_repo  # noqa: E402
from aicrm_next.channel_entry import repo as channel_entry_repo  # noqa: E402
from aicrm_next.channel_entry.application import callback_config  # noqa: E402
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


AUTHORIZATION_ENV = "AICRM_WECOM_CANARY_CHANNEL_IMPORT_AUTHORIZED"
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
SAFE_ID = re.compile(r"[A-Za-z0-9_.:@-]{1,256}\Z")
ASSET_FIELDS = frozenset(
    {
        "channel_name",
        "channel_code",
        "scene_value",
        "config_id",
        "qr_url",
        "qr_image_sha256",
        "owner_userid",
        "tag_id",
        "tag_name",
        "tag_group_name",
        "welcome_message",
        "source_repository",
        "source_release_sha",
    }
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import one pre-created production WeCom canary contact-way asset into ID validation.",
    )
    parser.add_argument("--asset-file", required=True)
    parser.add_argument("--spec-file", required=True)
    parser.add_argument("--expected-release-sha", required=True)
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--expected-policy-version", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--apply", action="store_true", default=False)
    parser.add_argument("--confirmation", default="")
    return parser.parse_args(argv)


def _private_json(path_value: str) -> dict[str, Any]:
    path = Path(str(path_value or "")).expanduser().resolve()
    if not path.is_file() or path.stat().st_size > 65536:
        raise ValueError("a bounded private asset file is required")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("asset file permissions must not grant group or other access")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("asset file must contain one JSON object")
    return payload


def _required_text(payload: dict[str, Any], field: str, *, maximum: int = 512) -> str:
    value = str(payload.get(field) or "").strip()
    if not value or len(value) > maximum or "\x00" in value:
        raise ValueError(f"invalid {field}")
    return value


def load_channel_asset(path_value: str) -> dict[str, str]:
    payload = _private_json(path_value)
    if set(payload) != ASSET_FIELDS:
        raise ValueError("channel asset fields do not match the exact private contract")
    asset = {field: _required_text(payload, field, maximum=2048 if field == "qr_url" else 512) for field in ASSET_FIELDS}
    for field in ("channel_code", "scene_value", "config_id", "owner_userid", "tag_id"):
        if SAFE_ID.fullmatch(asset[field]) is None:
            raise ValueError(f"invalid {field}")
    parsed_url = urlparse(asset["qr_url"])
    if parsed_url.scheme != "https" or parsed_url.hostname != "wework.qpic.cn":
        raise ValueError("qr_url must be one HTTPS WeCom QR asset")
    if re.fullmatch(r"[0-9a-f]{64}", asset["qr_image_sha256"]) is None:
        raise ValueError("qr_image_sha256 must be one SHA-256 digest")
    if asset["source_repository"] != "qianlan333/AI-CRM":
        raise ValueError("source repository must be the attested production callback owner")
    if FULL_SHA.fullmatch(asset["source_release_sha"]) is None:
        raise ValueError("source_release_sha must be one full SHA")
    return asset


def _confirmation(generation: int) -> str:
    return f"IMPORT_WECOM_CANARY_CHANNEL_{int(generation)}"


def _runtime_ready(*, database_url: str, generation: int, policy_version: str) -> None:
    state = RuntimeGenerationRepository(database_url).read_state()
    if (
        state.active_generation != int(generation)
        or not state.claim_enabled
        or state.policy_version != policy_version
        or state.external_claim_scope != "test_loopback"
    ):
        raise RuntimeError("channel import requires the exact active test-loopback generation")
    with open_runtime_connection(database_url) as connection:
        running = connection.execute(
            "SELECT COUNT(*)::BIGINT AS count FROM queue_runtime_soak_run WHERE status = 'running'"
        ).fetchone()
    if int((running or {}).get("count") or 0):
        raise RuntimeError("channel import is forbidden while a soak is running")


def _channel_data(asset: dict[str, str]) -> dict[str, Any]:
    return {
        "channel_type": "qrcode",
        "carrier_type": "qrcode",
        "channel_name": asset["channel_name"],
        "channel_code": asset["channel_code"],
        "scene_value": asset["scene_value"],
        "qr_url": asset["qr_url"],
        "status": "active",
        "owner_staff_id": asset["owner_userid"],
        "customer_channel": "",
        "link_url": "",
        "final_url": "",
        "welcome_message": asset["welcome_message"],
        "welcome_image_library_ids": [],
        "welcome_miniprogram_library_ids": [],
        "welcome_attachment_library_ids": [],
        "welcome_group_invite_library_ids": [],
        "auto_accept_friend": True,
        "entry_tag_id": asset["tag_id"],
        "entry_tag_name": asset["tag_name"],
        "entry_tag_group_name": asset["tag_group_name"],
        "assignment_mode": "single_owner",
        "assignment_strategy": "ratio",
        "overflow_policy": "least_loaded",
        "assignment_config_json": {},
    }


def _matching_channel(asset: dict[str, str]) -> dict[str, Any] | None:
    matches = [
        row
        for row in channels_repo.list_channels(limit=500, include_archived=True)
        if str(row.get("channel_code") or "").strip() == asset["channel_code"]
    ]
    if len(matches) > 1:
        raise RuntimeError("dedicated channel code is not unique")
    if not matches:
        return None
    channel = dict(matches[0])
    exact = {
        "channel_name": asset["channel_name"],
        "owner_staff_id": asset["owner_userid"],
        "entry_tag_id": asset["tag_id"],
        "welcome_message": asset["welcome_message"],
    }
    if any(str(channel.get(key) or "").strip() != value for key, value in exact.items()):
        raise RuntimeError("existing dedicated channel does not match the imported asset")
    return channel


def _apply(asset: dict[str, str], *, actor: str, reason: str) -> dict[str, Any]:
    if not channels_repo.uses_postgres():
        raise RuntimeError("channel import requires the production Postgres repository")
    existing = _matching_channel(asset)
    channel_id = int((existing or {}).get("id") or 0)
    if channel_id <= 0:
        channel_id = channels_repo.save_channel(_channel_data(asset))
    if channel_id <= 0:
        raise RuntimeError("channel import did not create a durable channel")

    corp_id = str(callback_config().get("corp_id") or "").strip()
    if not corp_id:
        raise RuntimeError("channel import requires the configured callback corp id")
    qrcode_asset = channel_entry_repo.insert_qrcode_asset(
        channel_id=channel_id,
        scene_value=asset["scene_value"],
        config_id=asset["config_id"],
        qr_url=asset["qr_url"],
        corp_id=corp_id,
        provider_payload_json={
            "imported": True,
            "qr_image_sha256": asset["qr_image_sha256"],
            "source_repository": asset["source_repository"],
            "source_release_sha": asset["source_release_sha"],
        },
        status="active",
        generation_source="id_validation_canary_import",
        created_by=actor,
    )
    if qrcode_asset.get("conflict"):
        raise RuntimeError(str(qrcode_asset.get("reason") or "qrcode asset import conflict"))
    qrcode_asset_id = int(qrcode_asset.get("id") or 0)
    if qrcode_asset_id <= 0:
        raise RuntimeError("channel import did not create a durable QR asset")
    channel_entry_repo.retire_active_qrcode_assets(channel_id, except_asset_id=qrcode_asset_id)
    alias = channel_entry_repo.upsert_channel_scene_alias(
        channel_id=channel_id,
        scene_value=asset["scene_value"],
        corp_id=corp_id,
        config_id=asset["config_id"],
        qr_url=asset["qr_url"],
        carrier_type="qrcode",
        status="active",
        source="id_validation_canary_import",
    )
    if alias.get("conflict"):
        raise RuntimeError(str(alias.get("reason") or "channel scene alias import conflict"))
    updated = channel_entry_repo.update_channel_qrcode(
        channel_id=channel_id,
        scene_value=asset["scene_value"],
        qr_url=asset["qr_url"],
        config_id=asset["config_id"],
    )
    if int(updated.get("id") or 0) != channel_id:
        raise RuntimeError("channel QR projection update failed")
    scene_hash = hashlib.sha256(asset["scene_value"].encode("utf-8")).hexdigest()
    channel_entry_repo.upsert_channel_entry_effect_log(
        effect_type="id_validation_channel_asset_import",
        idempotency_key=f"id-validation-channel-import:{scene_hash}",
        status="success",
        channel_id=channel_id,
        scene_value=asset["scene_value"],
        external_contact_id="",
        owner_staff_id=asset["owner_userid"],
        reason=reason,
        request_json={"target_values_redacted": True, "qr_image_sha256": asset["qr_image_sha256"]},
        response_json={
            "qrcode_asset_id": qrcode_asset_id,
            "scene_sha256": scene_hash,
            "source_repository": asset["source_repository"],
            "source_release_sha": asset["source_release_sha"],
            "real_external_call_executed": False,
        },
    )
    return {
        "channel_id": channel_id,
        "qrcode_asset_id": qrcode_asset_id,
        "scene_sha256": scene_hash,
        "reused_channel": bool(existing),
    }


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
    asset = load_channel_asset(args.asset_file)
    canary_spec = load_canary_spec(args.spec_file)
    if asset["owner_userid"] not in canary_spec["owner_userids"]:
        raise ValueError("channel owner is outside the private canary specification")
    plan = {
        "ok": True,
        "applied": False,
        "generation": int(args.generation),
        "policy_version": policy_version,
        "target_values_redacted": True,
        "real_external_call_executed": False,
    }
    if not args.apply:
        print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
        return 0
    if str(os.getenv(AUTHORIZATION_ENV) or "").strip() != "1":
        raise RuntimeError(f"{AUTHORIZATION_ENV}=1 is required")
    if str(args.confirmation or "").strip() != _confirmation(args.generation):
        raise RuntimeError(f"--confirmation must equal {_confirmation(args.generation)}")
    if current_release_sha() != release_sha:
        raise RuntimeError("active release SHA does not match the channel import request")
    database_url = normalize_runtime_database_url(raw_database_url())
    _runtime_ready(database_url=database_url, generation=int(args.generation), policy_version=policy_version)
    result = _apply(asset, actor=actor, reason=reason)
    print(json.dumps({**plan, **result, "applied": True}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
