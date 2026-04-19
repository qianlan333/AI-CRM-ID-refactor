from __future__ import annotations

import ast
import importlib
from pathlib import Path

from flask import Blueprint

from wecom_ability_service.http import HTTP_ROUTE_MODULES, HTTP_ROUTE_PLACEMENT, bp, register_http_routes


ROOT = Path(__file__).resolve().parents[1]
HTTP_REQUESTS_ALLOWLIST = {
    "wecom_ability_service.http.automation_conversion",
}


def test_routes_py_has_no_direct_bp_route_decorators():
    route_file = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "routes.py"
    module = ast.parse(route_file.read_text(encoding="utf-8"))

    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr != "route":
            continue
        owner = func.value
        if isinstance(owner, ast.Name) and owner.id == "bp":
            raise AssertionError("routes.py must not register routes directly")


def test_http_registration_exports_single_registry_contract():
    assert isinstance(bp, Blueprint)
    assert bp.name == "api"
    assert callable(register_http_routes)
    assert {
        "sidebar",
        "identity",
        "ops",
        "settings",
        "customer_center",
        "customer_timeline",
        "archive",
        "contacts",
        "group_chats",
        "callbacks",
        "tasks",
        "tags",
        "admin_user_ops",
        "admin_class_user",
        "admin_questionnaires",
        "public_questionnaires",
    }.issubset(HTTP_ROUTE_MODULES.keys())
    assert {"customer", "admin", "callbacks", "ops_settings"} == set(HTTP_ROUTE_PLACEMENT.keys())


def test_http_controller_modules_do_not_import_raw_sql_or_http_clients():
    forbidden_import_targets = {
        ("requests", None),
        ("wecom_ability_service.wecom_client", "WeComClient"),
    }

    for module_path in HTTP_ROUTE_MODULES.values():
        module = importlib.import_module(module_path)
        source_path = Path(module.__file__).resolve()
        parsed = ast.parse(source_path.read_text(encoding="utf-8"))
        allow_requests = module_path in HTTP_REQUESTS_ALLOWLIST

        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if (alias.name, None) == ("requests", None) and allow_requests:
                        continue
                    if (alias.name, None) in forbidden_import_targets:
                        raise AssertionError(f"{module_path} must not import {alias.name} directly")
            if isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                for alias in node.names:
                    if alias.name == "get_db" and module_name.endswith("db"):
                        raise AssertionError(f"{module_path} must not import get_db directly")
                    if module_name == "requests" or module_name.startswith("requests."):
                        if allow_requests:
                            continue
                        raise AssertionError(f"{module_path} must not import {alias.name} from {module_name}")
                    if (module_name, alias.name) in forbidden_import_targets:
                        raise AssertionError(f"{module_path} must not import {alias.name} from {module_name}")


def test_http_package_contains_no_raw_sql_calls():
    http_dir = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "http"
    for path in http_dir.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "get_db(" not in source, f"{path} must not call get_db() directly"
        assert ".execute(" not in source, f"{path} must not execute raw SQL directly"


def test_http_package_contains_no_direct_third_party_runtime_calls():
    http_dir = ROOT / "wecom_ability_service" / "http"
    for path in http_dir.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(ROOT).as_posix().replace("/", ".")[:-3]
        if relative_path not in HTTP_REQUESTS_ALLOWLIST:
            assert "import requests" not in source, f"{path} must not import requests directly"
            assert "requests." not in source, f"{path} must not call requests directly"
        assert "WeComClient.from_app(" not in source, f"{path} must not instantiate WeComClient.from_app() directly"
        assert "WeComClient.from_contact_app(" not in source, f"{path} must not instantiate WeComClient.from_contact_app() directly"
