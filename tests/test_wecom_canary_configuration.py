from __future__ import annotations

import json
from types import SimpleNamespace

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
    assert disabled["AICRM_WECOM_PRIVATE_ADAPTER_MODE"] == "disabled"
    assert disabled["AICRM_WECOM_GROUP_ADAPTER_MODE"] == "disabled"
    assert disabled["AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE"] == "false"


def test_enable_configuration_selects_production_adapters_only_for_enabled_message_types() -> None:
    spec = {field: tuple(_valid_spec()[field]) for field in configure_wecom_canary.LIST_FIELDS}
    enabled = configure_wecom_canary._settings_for_enable(spec)

    assert enabled["AICRM_WECOM_PRIVATE_ADAPTER_MODE"] == "production"
    assert enabled["AICRM_WECOM_GROUP_ADAPTER_MODE"] == "production"
    assert enabled["AICRM_ENABLE_REAL_WECOM_PRIVATE_MESSAGE"] == "true"
    assert enabled["AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE"] == "true"

    private_only = _valid_spec()
    private_only["enabled_effect_types"] = ["wecom.message.private.send"]
    private_only["group_chat_ids"] = []
    private_only["group_webhook_keys"] = []
    private_only["media_targets"] = []
    private_spec = {field: tuple(private_only[field]) for field in configure_wecom_canary.LIST_FIELDS}
    private = configure_wecom_canary._settings_for_enable(private_spec)

    assert private["AICRM_WECOM_PRIVATE_ADAPTER_MODE"] == "production"
    assert private["AICRM_WECOM_GROUP_ADAPTER_MODE"] == "disabled"
    assert private["AICRM_ENABLE_REAL_WECOM_PRIVATE_MESSAGE"] == "true"
    assert private["AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE"] == "false"


class _Rows:
    def __init__(self, *, one=None, many=None) -> None:
        self._one = one
        self._many = list(many or [])

    def fetchone(self):
        return self._one

    def fetchall(self):
        return list(self._many)


class _Transaction:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def __enter__(self):
        self._events.append("transaction_enter")
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._events.append("transaction_exit")


class _Connection:
    def __init__(self, events: list[str], control: dict) -> None:
        self._events = events
        self._control = control

    def __enter__(self):
        self._events.append("connection_enter")
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._events.append("connection_exit")

    def transaction(self) -> _Transaction:
        return _Transaction(self._events)

    def execute(self, statement, parameters=None) -> _Rows:
        sql = " ".join(str(statement).split())
        if "FROM queue_runtime_control" in sql and "FOR UPDATE" in sql:
            return _Rows(one=dict(self._control))
        if "SELECT key, value FROM app_settings" in sql:
            return _Rows(many=[])
        self._events.append("configuration_write")
        return _Rows()


class _Runtime:
    def __init__(self, events: list[str], *, scope: str) -> None:
        self._events = events
        self._scope = scope
        self.resume_arguments = None

    def read_state(self):
        return SimpleNamespace(
            active_generation=17,
            claim_enabled=True,
            policy_version="queue-v2-test-loopback",
            external_claim_scope=self._scope,
        )

    def disable_claims(self, **_kwargs):
        self._events.append("disable_claims")

    def wait_claims_drained(self, **_kwargs):
        self._events.append("wait_claims_drained")

    def resume_claims(self, **kwargs):
        self._events.append("resume_claims")
        self.resume_arguments = dict(kwargs)
        return SimpleNamespace(claim_enabled=True, external_claim_scope=self._scope)


def _patch_apply_runtime(monkeypatch, *, scope: str):
    events: list[str] = []
    runtime = _Runtime(events, scope=scope)
    control = {
        "active_generation": 17,
        "claim_enabled": False,
        "policy_version": "queue-v2-test-loopback",
        "external_claim_scope": scope,
    }
    monkeypatch.setenv(configure_wecom_canary.AUTHORIZATION_ENV, "1")
    monkeypatch.setattr(configure_wecom_canary, "raw_database_url", lambda: "postgresql://canary")
    monkeypatch.setattr(configure_wecom_canary, "normalize_runtime_database_url", lambda value: value)
    monkeypatch.setattr(configure_wecom_canary, "RuntimeGenerationRepository", lambda _url: runtime)
    monkeypatch.setattr(
        configure_wecom_canary,
        "open_runtime_connection",
        lambda _url: _Connection(events, control),
    )
    return events, runtime


def test_enable_configuration_resumes_exact_test_loopback_claim_gate_after_commit(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    events, runtime = _patch_apply_runtime(monkeypatch, scope="test_loopback")
    path = _write_spec(tmp_path, _valid_spec())

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
                "enable guarded canary",
                "--apply",
                "--confirmation",
                "CONFIGURE_WECOM_CANARY_17_ENABLE",
            ]
        )
        == 0
    )

    assert events.index("resume_claims") > events.index("connection_exit")
    assert runtime.resume_arguments == {
        "expected_generation": 17,
        "expected_policy_version": "queue-v2-test-loopback",
        "expected_scope": "test_loopback",
        "actor": "pytest",
        "reason": "canary configuration committed: enable guarded canary",
    }
    output = json.loads(capsys.readouterr().out)
    assert output["claim_enabled"] is True
    assert output["external_claim_scope"] == "test_loopback"
    assert output["provider_adapter_modes"] == {
        "private": "production",
        "group": "production",
    }


def test_disable_configuration_keeps_claim_gate_closed_for_scope_rollback(
    monkeypatch,
    capsys,
) -> None:
    events, runtime = _patch_apply_runtime(monkeypatch, scope="allowlisted")

    assert (
        configure_wecom_canary.main(
            [
                "--mode",
                "disable",
                "--generation",
                "17",
                "--expected-policy-version",
                "queue-v2-test-loopback",
                "--actor",
                "pytest",
                "--reason",
                "disable guarded canary",
                "--apply",
                "--confirmation",
                "CONFIGURE_WECOM_CANARY_17_DISABLE",
            ]
        )
        == 0
    )

    assert "resume_claims" not in events
    assert runtime.resume_arguments is None
    output = json.loads(capsys.readouterr().out)
    assert output["claim_enabled"] is False
    assert output["external_claim_scope"] == "allowlisted"
    assert output["provider_adapter_modes"] == {
        "private": "disabled",
        "group": "disabled",
    }
