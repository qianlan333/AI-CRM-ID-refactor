from __future__ import annotations

import json

from aicrm_next.platform_foundation.external_effects import wecom_canary_policy
from scripts.ops import plan_wecom_canary


def _spec() -> dict[str, tuple[str, ...]]:
    return {
        "external_userids": ("wm_canary_private",),
        "owner_userids": ("owner_canary",),
        "group_webhook_keys": ("group_canary",),
        "group_chat_ids": ("chat_canary",),
        "media_targets": ("image:7:image",),
        "enabled_effect_types": (
            "wecom.message.private.send",
            "wecom.message.group.send",
            "wecom.external_contact.detail.fetch",
            "wecom.media.upload",
        ),
    }


def _write_spec(tmp_path) -> str:
    path = tmp_path / "canary.json"
    path.write_text(json.dumps({key: list(value) for key, value in _spec().items()}))
    path.chmod(0o600)
    return str(path)


def test_plan_only_redacts_targets_and_never_plans_jobs(tmp_path, capsys) -> None:
    path = _write_spec(tmp_path)

    assert (
        plan_wecom_canary.main(
            [
                "--spec-file",
                path,
                "--run-id",
                "run-001",
                "--expected-release-sha",
                "a" * 40,
                "--generation",
                "17",
                "--expected-policy-version",
                "queue-v2-allowlisted",
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
    assert '"scenario_count": 4' in output
    assert '"target_values_redacted": true' in output
    for values in _spec().values():
        for value in values:
            assert value not in output


def test_canary_requests_require_post_plan_authorization_and_pass_exact_target_gates(monkeypatch) -> None:
    values = {
        wecom_canary_policy.WECOM_ALLOWED_EXTERNAL_USERIDS_KEY: {"wm_canary_private"},
        wecom_canary_policy.WECOM_ALLOWED_OWNER_USERIDS_KEY: {"owner_canary"},
        wecom_canary_policy.WECOM_ALLOWED_GROUP_WEBHOOK_KEYS_KEY: {"group_canary"},
        wecom_canary_policy.WECOM_ALLOWED_GROUP_CHAT_IDS_KEY: {"chat_canary"},
        wecom_canary_policy.WECOM_ALLOWED_MEDIA_TARGETS_KEY: {"image:7:image"},
    }
    monkeypatch.setattr(
        wecom_canary_policy,
        "runtime_setting",
        lambda key, default="": (
            "allowlisted_canary"
            if key == wecom_canary_policy.WECOM_PROVIDER_TARGET_POLICY_KEY
            else default
        ),
    )
    monkeypatch.setattr(
        wecom_canary_policy,
        "runtime_csv",
        lambda key: set(values.get(key, set())),
    )

    requests = plan_wecom_canary._scenario_requests(
        _spec(),
        run_id="run-001",
        scenarios=plan_wecom_canary.SCENARIOS,
    )

    assert len(requests) == 4
    assert {request["scenario"] for request in requests} == set(plan_wecom_canary.SCENARIOS)
    assert all("execution_scope" not in request["payload"] for request in requests)
    assert all("canary_authorization" not in request["payload_summary"] for request in requests)
    assert all(request["max_attempts"] == 1 for request in requests)
    group = next(request for request in requests if request["scenario"] == "group")
    assert group["payload"]["mention_all"] is False
