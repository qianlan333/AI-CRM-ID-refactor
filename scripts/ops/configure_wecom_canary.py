#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    from scripts.script_runtime import ensure_repo_root_on_path
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.script_runtime import ensure_repo_root_on_path

ensure_repo_root_on_path()

from aicrm_next.platform_foundation.execution_runtime.repository import (  # noqa: E402
    normalize_runtime_database_url,
    open_runtime_connection,
)
from aicrm_next.platform_foundation.execution_runtime.cutover import (  # noqa: E402
    RuntimeGenerationRepository,
)
from aicrm_next.platform_foundation.execution_runtime.validation import (  # noqa: E402
    CANARY_CONFIG_KEYS,
    configuration_hash,
)
from aicrm_next.platform_foundation.external_effects.adapters import (  # noqa: E402
    WECOM_EFFECT_TYPES,
)
from aicrm_next.platform_foundation.external_effects.models import (  # noqa: E402
    WECOM_MEDIA_UPLOAD,
    WECOM_MESSAGE_GROUP_SEND,
    WECOM_MESSAGE_PRIVATE_SEND,
)
from aicrm_next.shared.runtime import raw_database_url  # noqa: E402


AUTHORIZATION_ENV = "AICRM_WECOM_CANARY_CONFIG_AUTHORIZED"
POLICY_KEY = "AICRM_WECOM_PROVIDER_TARGET_POLICY"
EXTERNAL_TARGETS_KEY = "AICRM_EXTERNAL_EFFECT_ALLOWED_TARGET_EXTERNAL_USERIDS"
OWNERS_KEY = "AICRM_EXTERNAL_EFFECT_ALLOWED_OWNER_USERIDS"
GROUP_WEBHOOK_KEYS_KEY = "AICRM_EXTERNAL_EFFECT_ALLOWED_GROUP_OPS_WEBHOOK_KEYS"
GROUP_CHAT_IDS_KEY = "AICRM_EXTERNAL_EFFECT_ALLOWED_GROUP_CHAT_IDS"
MEDIA_TARGETS_KEY = "AICRM_WECOM_CANARY_ALLOWED_MEDIA_TARGETS"
DEFAULT_SENDER_KEY = "AICRM_WECOM_DEFAULT_SENDER_USERID"
ENABLED_TYPES_KEY = "AICRM_WECOM_ENABLED_EFFECT_TYPES"
TRACKED_KEYS = CANARY_CONFIG_KEYS
LIST_FIELDS = (
    "external_userids",
    "owner_userids",
    "group_webhook_keys",
    "group_chat_ids",
    "media_targets",
    "enabled_effect_types",
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Configure the fail-closed ID-validation WeCom canary target policy.",
    )
    parser.add_argument("--mode", choices=("enable", "disable"), required=True)
    parser.add_argument("--spec-file", default="")
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--expected-policy-version", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--apply", action="store_true", default=False)
    parser.add_argument("--confirmation", default="")
    return parser.parse_args(argv)


def _confirmation(args: argparse.Namespace) -> str:
    return f"CONFIGURE_WECOM_CANARY_{int(args.generation)}_{str(args.mode).upper()}"


def _safe_value(value: Any, *, field: str) -> str:
    normalized = str(value or "").strip()
    if (
        not normalized
        or len(normalized) > 256
        or any(character.isspace() for character in normalized)
        or "," in normalized
        or normalized in {"*", "all", "ALL"}
    ):
        raise ValueError(f"invalid {field} entry")
    return normalized


def _list(spec: dict[str, Any], field: str) -> tuple[str, ...]:
    raw = spec.get(field, [])
    if not isinstance(raw, list):
        raise ValueError(f"{field} must be an array")
    values = tuple(dict.fromkeys(_safe_value(item, field=field) for item in raw))
    if len(values) > 50:
        raise ValueError(f"{field} exceeds the canary limit")
    return values


def load_canary_spec(path_value: str) -> dict[str, tuple[str, ...]]:
    path = Path(str(path_value or "")).expanduser().resolve()
    if not path.is_file():
        raise ValueError("a private --spec-file is required for enable mode")
    if path.stat().st_size > 65536:
        raise ValueError("canary spec is too large")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("canary spec permissions must not grant group or other access")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("canary spec must be a JSON object")
    unknown = set(payload) - set(LIST_FIELDS)
    if unknown:
        raise ValueError("canary spec contains unsupported fields")
    result = {field: _list(payload, field) for field in LIST_FIELDS}
    effect_types = set(result["enabled_effect_types"])
    if not effect_types or not effect_types.issubset(set(WECOM_EFFECT_TYPES)):
        raise ValueError("enabled_effect_types must be a non-empty supported WeCom subset")
    if effect_types & {
        WECOM_MESSAGE_PRIVATE_SEND,
        "wecom.welcome_message.send",
        "wecom.contact.tag.mark",
        "wecom.contact.tag.unmark",
        "wecom.profile.update",
        "wecom.external_contact.detail.fetch",
    } and not result["external_userids"]:
        raise ValueError("the selected effects require external_userids")
    if effect_types & {
        WECOM_MESSAGE_PRIVATE_SEND,
        WECOM_MESSAGE_GROUP_SEND,
        "wecom.welcome_message.send",
        "wecom.contact.tag.mark",
        "wecom.contact.tag.unmark",
        "wecom.profile.update",
    } and not result["owner_userids"]:
        raise ValueError("the selected effects require owner_userids")
    if WECOM_MESSAGE_GROUP_SEND in effect_types and not result["group_chat_ids"]:
        raise ValueError("group message canary requires group_chat_ids")
    if WECOM_MEDIA_UPLOAD in effect_types and not result["media_targets"]:
        raise ValueError("media canary requires media_targets")
    return result


def _settings_for_enable(spec: dict[str, tuple[str, ...]]) -> dict[str, str]:
    effect_types = set(spec["enabled_effect_types"])
    return {
        POLICY_KEY: "allowlisted_canary",
        EXTERNAL_TARGETS_KEY: ",".join(spec["external_userids"]),
        OWNERS_KEY: ",".join(spec["owner_userids"]),
        GROUP_WEBHOOK_KEYS_KEY: ",".join(spec["group_webhook_keys"]),
        GROUP_CHAT_IDS_KEY: ",".join(spec["group_chat_ids"]),
        MEDIA_TARGETS_KEY: ",".join(spec["media_targets"]),
        DEFAULT_SENDER_KEY: spec["owner_userids"][0] if spec["owner_userids"] else "",
        ENABLED_TYPES_KEY: ",".join(spec["enabled_effect_types"]),
        "AICRM_WECOM_EXECUTION_MODE": "execute",
        "AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE": "true",
        "AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY": "false",
        "AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED": "true",
        "AICRM_ENABLE_REAL_WECOM_PRIVATE_MESSAGE": (
            "true" if WECOM_MESSAGE_PRIVATE_SEND in effect_types else "false"
        ),
        "AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE": (
            "true" if WECOM_MESSAGE_GROUP_SEND in effect_types else "false"
        ),
        "AICRM_EXTERNAL_EFFECT_MEDIA_UPLOAD_EXECUTE": (
            "true" if WECOM_MEDIA_UPLOAD in effect_types else "false"
        ),
    }


def _settings_for_disable() -> dict[str, str]:
    return {
        POLICY_KEY: "blocked",
        EXTERNAL_TARGETS_KEY: "",
        OWNERS_KEY: "",
        GROUP_WEBHOOK_KEYS_KEY: "",
        GROUP_CHAT_IDS_KEY: "",
        MEDIA_TARGETS_KEY: "",
        DEFAULT_SENDER_KEY: "",
        ENABLED_TYPES_KEY: "",
        "AICRM_WECOM_EXECUTION_MODE": "disabled",
        "AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE": "false",
        "AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY": "true",
        "AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED": "true",
        "AICRM_ENABLE_REAL_WECOM_PRIVATE_MESSAGE": "false",
        "AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE": "false",
        "AICRM_EXTERNAL_EFFECT_MEDIA_UPLOAD_EXECUTE": "false",
    }


def _counts(spec: dict[str, tuple[str, ...]] | None) -> dict[str, int]:
    source = spec or {field: () for field in LIST_FIELDS}
    return {field: len(source[field]) for field in LIST_FIELDS}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if int(args.generation) <= 0:
        raise ValueError("generation must be positive")
    if not str(args.expected_policy_version or "").strip():
        raise ValueError("expected_policy_version is required")
    if not str(args.actor or "").strip() or not str(args.reason or "").strip():
        raise ValueError("actor and reason are required")
    spec = load_canary_spec(args.spec_file) if args.mode == "enable" else None
    desired = _settings_for_enable(spec or {}) if spec is not None else _settings_for_disable()
    plan = {
        "ok": True,
        "applied": False,
        "mode": str(args.mode),
        "generation": int(args.generation),
        "expected_policy_version": str(args.expected_policy_version),
        "allowlist_counts": _counts(spec),
        "enabled_effect_type_count": len((spec or {}).get("enabled_effect_types", ())),
        "target_values_redacted": True,
        "real_external_call_executed": False,
    }
    if not args.apply:
        print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
        return 0
    if str(os.getenv(AUTHORIZATION_ENV) or "").strip() != "1":
        raise RuntimeError(f"{AUTHORIZATION_ENV}=1 is required")
    if str(args.confirmation or "").strip() != _confirmation(args):
        raise RuntimeError(f"--confirmation must equal {_confirmation(args)}")

    database_url = normalize_runtime_database_url(raw_database_url())
    runtime = RuntimeGenerationRepository(database_url)
    state = runtime.read_state()
    allowed_scopes = {"test_loopback"} if args.mode == "enable" else {"allowlisted", "test_loopback"}
    if (
        state.active_generation != int(args.generation)
        or state.policy_version != str(args.expected_policy_version)
        or state.external_claim_scope not in allowed_scopes
    ):
        raise RuntimeError("canary configuration runtime state does not match the exact request")
    if state.claim_enabled:
        runtime.disable_claims(
            expected_generation=int(args.generation),
            actor=str(args.actor),
            reason=f"canary configuration drain: {str(args.reason)}",
        )
    runtime.wait_claims_drained(timeout_seconds=60)
    with open_runtime_connection(database_url) as connection:
        with connection.transaction():
            control = connection.execute(
                """
                SELECT active_generation, claim_enabled, policy_version, external_claim_scope
                FROM queue_runtime_control
                WHERE singleton = TRUE
                FOR UPDATE
                """
            ).fetchone()
            if not control:
                raise RuntimeError("queue runtime control row is missing")
            if (
                int(control.get("active_generation") or 0) != int(args.generation)
                or bool(control.get("claim_enabled"))
                or str(control.get("policy_version") or "") != str(args.expected_policy_version)
            ):
                raise RuntimeError("canary configuration requires the exact closed generation and policy")
            if str(control.get("external_claim_scope") or "") not in allowed_scopes:
                raise RuntimeError("canary configuration scope changed before the transaction")

            rows = connection.execute(
                "SELECT key, value FROM app_settings WHERE key = ANY(%s)",
                (list(TRACKED_KEYS),),
            ).fetchall()
            before = {key: "" for key in TRACKED_KEYS}
            before.update({str(row.get("key") or ""): str(row.get("value") or "") for row in rows})
            for key, value in desired.items():
                connection.execute(
                    """
                    INSERT INTO app_settings (key, value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (key, value),
                )
            after = dict(before)
            after.update(desired)
            connection.execute(
                """
                INSERT INTO queue_runtime_canary_config_audit (
                    config_audit_id, active_generation, policy_version, config_mode,
                    config_hash_before, config_hash_after, allowlist_counts_json,
                    actor, reason
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                """,
                (
                    "qrca_" + uuid4().hex,
                    int(args.generation),
                    str(args.expected_policy_version),
                    str(args.mode),
                    configuration_hash(before),
                    configuration_hash(after),
                    json.dumps(_counts(spec), sort_keys=True),
                    str(args.actor).strip(),
                    str(args.reason).strip(),
                ),
            )
    print(
        json.dumps(
            {
                **plan,
                "applied": True,
                "configuration_hash": configuration_hash(after),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
