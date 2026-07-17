from __future__ import annotations

import pytest

from aicrm_next.admin_config.application import AdminConfigWriteCommand


CONTROLLED_ERROR = "setting is controlled by ID-validation queue operation"


class _ActiveCanaryRepository:
    def get_app_setting(self, key: str):
        assert key == "AICRM_WECOM_PROVIDER_TARGET_POLICY"
        return {"value": "allowlisted_canary"}


def test_generic_app_setting_command_rejects_id_validation_canary_keys_before_writing() -> None:
    command = AdminConfigWriteCommand(repo=_ActiveCanaryRepository())

    with pytest.raises(ValueError, match=CONTROLLED_ERROR):
        command.execute(
            {"AICRM_WECOM_PROVIDER_TARGET_POLICY": "allowlisted_canary"},
            operator="pytest",
        )


def test_category_setting_command_rejects_id_validation_canary_keys_before_writing() -> None:
    command = AdminConfigWriteCommand(repo=_ActiveCanaryRepository())

    with pytest.raises(ValueError, match=CONTROLLED_ERROR):
        command.save_category_settings(
            "webhooks_push",
            {"AICRM_EXTERNAL_EFFECT_ALLOWED_TARGET_EXTERNAL_USERIDS": "wm_target"},
            operator="pytest",
        )


def test_push_capability_toggle_cannot_rederive_canary_execution_gates() -> None:
    command = AdminConfigWriteCommand(repo=_ActiveCanaryRepository())

    with pytest.raises(ValueError, match=CONTROLLED_ERROR):
        command.set_push_capability_enabled("wecom_private_message", True, operator="pytest")
