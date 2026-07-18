from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest

from scripts.ops import import_wecom_canary_media_asset as media_import


RELEASE_SHA = "a" * 40
POLICY_VERSION = "queue-v2-test-loopback-canary"


def _spec() -> dict:
    return {
        "external_userids": ["external_private_value"],
        "owner_userids": ["owner_private_value"],
        "group_webhook_keys": [],
        "group_chat_ids": [],
        "media_targets": ["image:111:image"],
        "enabled_effect_types": ["wecom.media.upload"],
    }


def _write_spec(tmp_path) -> str:
    path = tmp_path / "canary.json"
    path.write_text(json.dumps(_spec()), encoding="utf-8")
    path.chmod(0o600)
    return str(path)


def _argv(spec_path: str) -> list[str]:
    return [
        "--spec-file",
        spec_path,
        "--expected-release-sha",
        RELEASE_SHA,
        "--generation",
        "1",
        "--expected-policy-version",
        POLICY_VERSION,
        "--actor",
        "pytest",
        "--reason",
        "dedicated media import",
    ]


def test_media_import_plan_is_local_only_and_redacts_spec(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        media_import,
        "raw_database_url",
        lambda: pytest.fail("plan-only media import must not read the database"),
    )

    assert media_import.main(_argv(_write_spec(tmp_path))) == 0

    output = capsys.readouterr().out
    assert '"applied": false' in output
    assert '"deterministic_local_source": true' in output
    assert '"real_external_call_executed": false' in output
    assert '"target_values_redacted": true' in output
    for values in _spec().values():
        for value in values:
            assert value not in output


def test_media_import_apply_requires_exact_authorization(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(media_import.AUTHORIZATION_ENV, raising=False)

    with pytest.raises(RuntimeError, match=media_import.AUTHORIZATION_ENV):
        media_import.main(
            [
                *_argv(_write_spec(tmp_path)),
                "--apply",
                "--confirmation",
                "IMPORT_WECOM_CANARY_MEDIA_1",
            ]
        )


def test_media_import_requires_exact_image_to_image_target() -> None:
    invalid = _spec()
    invalid["media_targets"] = ["attachment:111:attachment"]

    with pytest.raises(ValueError, match="image material uploaded as image"):
        media_import._require_image_canary_target(invalid)


class _Repository:
    def __init__(self) -> None:
        self.item: dict | None = None
        self.save_count = 0

    def list_items(self, kind, *, limit, offset, filters):
        assert kind == "image"
        assert filters["enabled_only"] is False
        return {"items": [] if self.item is None else [dict(self.item)]}

    def get_item(self, kind, item_id, *, include_data=True):
        assert kind == "image"
        assert include_data is True
        return dict(self.item or {})

    def save_item(self, kind, payload, item_id=None):
        assert kind == "image"
        assert item_id is None
        self.save_count += 1
        self.item = {
            "id": 712,
            "name": media_import.MATERIAL_NAME,
            "enabled": True,
            "mime_type": "image/png",
            "data_base64": str(payload["data_base64"]),
        }
        return dict(self.item)


def test_media_import_apply_is_idempotent_and_returns_non_sensitive_material_id(tmp_path, monkeypatch, capsys) -> None:
    repository = _Repository()
    monkeypatch.setenv(media_import.AUTHORIZATION_ENV, "1")
    monkeypatch.setattr(media_import, "current_release_sha", lambda: RELEASE_SHA)
    monkeypatch.setattr(media_import, "raw_database_url", lambda: "postgresql://example.invalid/aicrm")
    monkeypatch.setattr(media_import, "_runtime_ready", lambda **kwargs: None)
    monkeypatch.setattr(media_import, "PostgresMediaLibraryRepository", lambda database_url: repository)
    apply_args = [
        *_argv(_write_spec(tmp_path)),
        "--apply",
        "--confirmation",
        "IMPORT_WECOM_CANARY_MEDIA_1",
    ]

    assert media_import.main(apply_args) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["created"] is True
    assert first["material_id"] == 712
    assert first["canary_spec_update_required"] is True
    assert first["real_external_call_executed"] is False

    assert media_import.main(apply_args) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["created"] is False
    assert second["material_id"] == 712
    assert repository.save_count == 1


def test_canary_png_is_deterministic_and_validly_framed() -> None:
    payload = media_import.canary_png_bytes()

    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert payload.endswith(b"IEND\xaeB`\x82")
    assert base64.b64decode(base64.b64encode(payload)) == payload


def test_runtime_gate_requires_test_loopback(monkeypatch) -> None:
    monkeypatch.setattr(
        media_import,
        "RuntimeGenerationRepository",
        lambda database_url: SimpleNamespace(
            read_state=lambda: SimpleNamespace(
                active_generation=1,
                claim_enabled=True,
                policy_version=POLICY_VERSION,
                external_claim_scope="allowlisted",
            )
        ),
    )

    with pytest.raises(RuntimeError, match="test-loopback"):
        media_import._runtime_ready(
            database_url="postgresql://example.invalid/aicrm",
            generation=1,
            policy_version=POLICY_VERSION,
        )
