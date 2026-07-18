from __future__ import annotations

import json

import pytest

from scripts.ops import configure_wecom_canary


def _write_spec(tmp_path, payload: dict) -> str:
    path = tmp_path / "canary.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)
    return str(path)


def _valid_spec() -> dict:
    return {
        "external_userids": ["wm_canary_private"],
        "owner_userids": ["owner_canary"],
        "group_webhook_keys": ["group_canary"],
        "group_chat_ids": ["chat_canary"],
        "media_targets": ["image:7:image"],
        "enabled_effect_types": [
            "wecom.message.private.send",
            "wecom.message.group.send",
            "wecom.media.upload",
        ],
    }


def test_canary_configuration_plan_redacts_all_target_values(tmp_path, capsys) -> None:
    spec = _valid_spec()
    path = _write_spec(tmp_path, spec)

    assert (
        configure_wecom_canary.main(
            [
                "--mode",
                "enable",
                "--spec-file",
                path,
                "--generation",
                "17",
                "--expected-policy-version",
                "queue-v2-test-loopback",
                "--actor",
                "pytest",
                "--reason",
                "plan only",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert '"applied": false' in output
    assert '"target_values_redacted": true' in output
    assert '"external_userids": 1' in output
    for values in spec.values():
        for value in values:
            assert value not in output


def test_canary_configuration_rejects_wildcards_and_incomplete_group_scope(tmp_path) -> None:
    wildcard = _valid_spec()
    wildcard["external_userids"] = ["*"]
    with pytest.raises(ValueError, match="invalid external_userids entry"):
        configure_wecom_canary.load_canary_spec(_write_spec(tmp_path, wildcard))

    incomplete = _valid_spec()
    incomplete["group_chat_ids"] = []
    with pytest.raises(ValueError, match="group message canary requires group_chat_ids"):
        configure_wecom_canary.load_canary_spec(_write_spec(tmp_path, incomplete))


def test_canary_configuration_requires_private_spec_permissions(tmp_path) -> None:
    path = tmp_path / "canary.json"
    path.write_text(json.dumps(_valid_spec()), encoding="utf-8")
    path.chmod(0o644)

    with pytest.raises(ValueError, match="permissions"):
        configure_wecom_canary.load_canary_spec(str(path))


def test_canary_configuration_apply_requires_exact_authorization(tmp_path, monkeypatch) -> None:
    path = _write_spec(tmp_path, _valid_spec())
    monkeypatch.delenv(configure_wecom_canary.AUTHORIZATION_ENV, raising=False)

    with pytest.raises(RuntimeError, match="AICRM_WECOM_CANARY_CONFIG_AUTHORIZED=1"):
        configure_wecom_canary.main(
            [
                "--mode",
                "enable",
                "--spec-file",
                path,
                "--generation",
                "17",
                "--expected-policy-version",
                "queue-v2-test-loopback",
                "--actor",
                "pytest",
                "--reason",
                "explicit apply",
                "--apply",
                "--confirmation",
                "CONFIGURE_WECOM_CANARY_17_ENABLE",
            ]
        )


def test_disable_configuration_clears_every_real_target_and_provider_gate() -> None:
    disabled = configure_wecom_canary._settings_for_disable()

    assert disabled[configure_wecom_canary.POLICY_KEY] == "blocked"
    for key in (
        configure_wecom_canary.EXTERNAL_TARGETS_KEY,
        configure_wecom_canary.OWNERS_KEY,
        configure_wecom_canary.GROUP_WEBHOOK_KEYS_KEY,
        configure_wecom_canary.GROUP_CHAT_IDS_KEY,
        configure_wecom_canary.MEDIA_TARGETS_KEY,
        configure_wecom_canary.DEFAULT_SENDER_KEY,
        configure_wecom_canary.ENABLED_TYPES_KEY,
    ):
        assert disabled[key] == ""
    assert disabled["AICRM_WECOM_EXECUTION_MODE"] == "disabled"
    assert disabled["AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE"] == "false"
