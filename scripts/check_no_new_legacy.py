#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.platform_foundation.route_registry.checker import build_route_check_report
from aicrm_next.platform_foundation.route_registry.service import RouteRegistryService

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".venv310",
    "__pycache__",
    "docs",
    "migrations",
    "tests",
    "tools",
    "skills",
    "experiments",
    "wecom_ability_service",
    "scripts",
}
LEGACY_IMPORT_ALLOWLIST = {
    Path("aicrm_next/production_compat/api.py"),
    Path("aicrm_next/frontend_compat/legacy_routes.py"),
    Path("aicrm_next/questionnaire/api.py"),
    Path("aicrm_next/automation_engine/group_ops/action_port.py"),
    Path("aicrm_next/automation_engine/group_ops/domain.py"),
    Path("aicrm_next/ai_assist/external_campaigns.py"),
    Path("aicrm_next/integration_gateway/legacy_flask_facade.py"),
    Path("aicrm_next/integration_gateway/legacy_customer_read_facade.py"),
    Path("aicrm_next/integration_gateway/legacy_automation_facade.py"),
    Path("aicrm_next/integration_gateway/legacy_questionnaire_facade.py"),
    Path("aicrm_next/integration_gateway/legacy_sidebar_read_facade.py"),
    Path("aicrm_next/integration_gateway/wecom_group_adapter.py"),
}
WECOM_IMPORT_ALLOWLIST = {
    Path("app.py"),
    Path("legacy_flask_app.py"),
    Path("aicrm_next/automation_engine/audience_transition/repository.py"),
    Path("aicrm_next/automation_engine/audience_transition/integration_gateway.py"),
    Path("aicrm_next/automation_engine/audience_transition/application.py"),
    Path("aicrm_next/automation_engine/group_ops/integration_gateway.py"),
    Path("aicrm_next/automation_engine/group_ops/scheduler.py"),
    Path("aicrm_next/automation_engine/group_ops/action_port.py"),
    Path("aicrm_next/ai_assist/external_campaigns.py"),
    Path("aicrm_next/integration_gateway/questionnaire_adapters.py"),
    Path("aicrm_next/integration_gateway/wecom_group_adapter.py"),
    Path("aicrm_next/cloud_orchestrator/repository.py"),
}
API_SIDE_EFFECT_ALLOWLIST = {
    Path("aicrm_next/production_compat/api.py"),
}
SIDE_EFFECT_MARKERS = {
    "dispatch_wecom_task",
    "create_contact_way",
    "requests.post(",
    "requests.put(",
    "requests.patch(",
    "requests.delete(",
    "httpx.post(",
    "httpx.put(",
    "httpx.patch(",
    "httpx.delete(",
}


@dataclass(frozen=True)
class Violation:
    code: str
    path: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _iter_python_files(root: Path) -> Iterable[Path]:
    candidates: list[Path] = []
    for item in [root / "aicrm_next", root / "app.py", root / "legacy_flask_app.py"]:
        if item.is_file():
            candidates.append(item)
        elif item.is_dir():
            candidates.extend(item.rglob("*.py"))
    for path in candidates:
        parts = set(path.relative_to(root).parts)
        if parts & EXCLUDED_DIRS:
            continue
        yield path


def scan_source_tree(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    for path in _iter_python_files(root):
        rel = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        if "legacy_flask_facade" in text and rel not in LEGACY_IMPORT_ALLOWLIST:
            violations.append(Violation("legacy_flask_facade_import", str(rel), "legacy Flask facade import is not allowlisted"))
        if "wecom_ability_service" in text and rel not in WECOM_IMPORT_ALLOWLIST:
            violations.append(Violation("wecom_ability_service_import", str(rel), "legacy wecom_ability_service import is not allowlisted"))
        if rel.name in {"api.py", "routes.py"} and rel not in API_SIDE_EFFECT_ALLOWLIST:
            for marker in SIDE_EFFECT_MARKERS:
                if marker in text:
                    violations.append(Violation("api_direct_external_side_effect", str(rel), marker))
    return violations


def _decorator_route_paths(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    route_paths: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            attr = decorator.func
            if not isinstance(attr, ast.Attribute) or attr.attr != "api_route":
                continue
            if not decorator.args:
                continue
            first = decorator.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                route_paths.append(first.value)
    return route_paths


def check_production_compat_routes(root: Path = ROOT) -> list[Violation]:
    service = RouteRegistryService()
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    for route_path in _decorator_route_paths(compat_path):
        entry = service.find_route(route_path, None)
        if not entry:
            violations.append(Violation("production_compat_route_not_registered", str(compat_path.relative_to(root)), route_path))
            continue
        if entry.runtime_owner != "production_compat" and not entry.legacy_fallback_allowed:
            violations.append(Violation("production_compat_route_owner_mismatch", str(compat_path.relative_to(root)), route_path))
        if "{path:path}" in route_path and not entry.legacy_fallback_allowed:
            violations.append(Violation("undocumented_wildcard_fallback", str(compat_path.relative_to(root)), route_path))
    return violations


def run_checks(*, strict: bool) -> dict:
    violations = scan_source_tree(ROOT) + check_production_compat_routes(ROOT)
    route_report = build_route_check_report(strict=strict)
    for item in route_report["blockers"]:
        violations.append(Violation("route_registry_strict", "runtime", str(item)))
    return {
        "ok": not violations,
        "strict": strict,
        "violations": [violation.to_dict() for violation in violations],
        "route_registry": {
            "ok": route_report["ok"],
            "mode": route_report["mode"],
            "registered_routes_count": route_report["registered_routes_count"],
            "manifest_routes_count": route_report["manifest_routes_count"],
            "undocumented_routes_count": len(route_report["undocumented_routes"]),
            "legacy_fallback_routes_count": len(route_report["legacy_fallback_routes"]),
            "wildcard_routes_count": len(route_report["wildcard_routes"]),
            "unknown_owner_routes_count": len(route_report["unknown_owner_routes"]),
            "deleted_but_still_registered_routes_count": len(route_report["deleted_but_still_registered_routes"]),
            "blockers": route_report["blockers"],
            "warnings": route_report["warnings"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Block new legacy imports, fallbacks, wildcard routes, and undocumented Next routes.")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = run_checks(strict=bool(args.strict))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
