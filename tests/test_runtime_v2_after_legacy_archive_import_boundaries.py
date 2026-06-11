from __future__ import annotations

import importlib
import sys


def test_runtime_v2_import_boundaries_after_legacy_http_archive(monkeypatch):
    monkeypatch.setitem(sys.modules, "wecom_ability_service.observability", None)

    modules = [
        "aicrm_next.automation_engine.channels_api",
        "aicrm_next.channel_entry.application",
        "aicrm_next.automation_runtime_v2.bridge",
        "scripts.smoke_automation_runtime_v2",
    ]

    for module_name in modules:
        importlib.import_module(module_name)


def test_smoke_harness_has_no_legacy_app_factory_dependency():
    smoke = importlib.import_module("scripts.smoke_automation_runtime_v2")

    assert not hasattr(smoke.SmokeRunner, "_push_flask_context")
