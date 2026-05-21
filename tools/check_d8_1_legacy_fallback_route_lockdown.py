#!/usr/bin/env python
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

Json = dict[str, Any]

FORBIDDEN_STATUS_MARKERS = ["delete_ready", "production_ready", "production_approved"]

REQUIRED_RETIRED_GROUP_TERMS = {
    "media": ["image-library", "attachment-library", "miniprogram-library"],
    "product": ["wechat-pay/products"],
    "customer": ["/api/customers", "/admin/customers"],
    "user_ops": ["/api/admin/user-ops/overview", "/api/admin/user-ops/list", "/api/admin/user-ops/send-records"],
    "questionnaire": ["/api/admin/questionnaires", "/admin/questionnaires", "/s/{slug}", "/api/h5/questionnaires/{slug}"],
    "automation": ["/admin/automation-conversion", "/api/admin/automation-conversion/overview", "/api/admin/automation-conversion/pools", "/api/admin/automation-conversion/members", "/api/admin/automation-conversion/execution-records"],
}

DOCS_TO_SCAN = [
    "docs/d8_legacy_flask_shell_retirement_plan.md",
    "docs/d8_legacy_shell_dependency_inventory.md",
    "docs/d8_legacy_shell_allowed_fallback_matrix.md",
    "docs/d8_1_legacy_fallback_route_lockdown_plan.md",
    "docs/d8_1_legacy_fallback_route_matrix.md",
    "docs/legacy_retirement_plan.md",
    "docs/legacy_delete_batches.md",
    "docs/legacy_route_owner_cutover_matrix.md",
    "docs/module_status_matrix.md",
    "docs/remaining_work_queue.md",
    "docs/go_no_go_checklist.md",
]


def _path(relpath: str) -> Path:
    return PROJECT_ROOT / relpath


def _read(relpath: str) -> str:
    return _path(relpath).read_text(encoding="utf-8")


def _clean_cell(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`") and len(value) >= 2:
        value = value[1:-1]
    return value.strip()


def parse_matrix(path: Path) -> list[Json]:
    if not path.exists():
        raise FileNotFoundError(path)
    rows: list[Json] = []
    header: list[str] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [_clean_cell(cell) for cell in line.strip("|").split("|")]
        if header is None:
            if "route_or_pattern" in cells:
                header = cells
            continue
        if all(re.fullmatch(r"-+", cell.strip()) for cell in cells):
            continue
        if len(cells) != len(header):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _literal_methods(node: ast.AST | None) -> set[str]:
    if node is None:
        return {"GET"}
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values = {_literal_string(item) for item in node.elts}
        return {value.upper() for value in values if value}
    value = _literal_string(node)
    if value:
        return {value.upper()}
    return {"GET"}


def build_static_legacy_route_map() -> list[Json]:
    route_map: list[Json] = []
    http_root = _path("wecom_ability_service/http")
    if not http_root.exists():
        return route_map
    for path in sorted(http_root.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and func.attr == "route"
                and isinstance(func.value, ast.Name)
                and func.value.id == "bp"
            ):
                continue
            if not node.args:
                continue
            route = _literal_string(node.args[0])
            if not route:
                continue
            methods_node = None
            for keyword in node.keywords:
                if keyword.arg == "methods":
                    methods_node = keyword.value
                    break
            for method in sorted(_literal_methods(methods_node)):
                route_map.append(
                    {
                        "method": method,
                        "path": route,
                        "source": path.relative_to(PROJECT_ROOT).as_posix(),
                    }
                )
    return route_map


def _normalize_route_pattern(pattern: str) -> str:
    pattern = pattern.strip()
    pattern = re.sub(r"\s+\(.*\)$", "", pattern)
    return pattern


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    pattern = _normalize_route_pattern(pattern)
    wildcard_suffix = pattern.endswith("*")
    if wildcard_suffix:
        pattern = pattern[:-1]
    escaped = re.escape(pattern)
    escaped = re.sub(r"\\\{[^/]+\\\}", r"[^/]+", escaped)
    escaped = re.sub(r"<(?:[^:>/]+:)?[^>/]+>", r"[^/]+", escaped)
    if wildcard_suffix:
        return re.compile("^" + escaped)
    return re.compile("^" + escaped + "$")


def _exclusion_patterns(row: Json) -> list[re.Pattern[str]]:
    text = f"{row.get('reason', '')} {row.get('notes', '')}"
    patterns = re.findall(r"`([^`]+)`", text) if "Excluding" in text or "excluding" in text else []
    return [_pattern_to_regex(pattern) for pattern in patterns]


def _row_expected_bool(row: Json) -> bool | None:
    value = str(row.get("legacy_registration_expected", "")).strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _matches_row(row: Json, route: Json) -> bool:
    row_method = str(row.get("method", "")).upper().strip()
    if row_method not in {"*", "ANY", route["method"]}:
        return False
    pattern = str(row.get("route_or_pattern", "")).strip()
    if not pattern.startswith("/"):
        return False
    if not _pattern_to_regex(pattern).search(route["path"]):
        return False
    return not any(exclusion.search(route["path"]) for exclusion in _exclusion_patterns(row))


def _check_matrix(rows: list[Json], blockers: list[Json]) -> tuple[list[Json], list[Json], Json]:
    retired_rows = [row for row in rows if row.get("category") == "retired_readonly_route"]
    allowed_rows = [row for row in rows if row.get("category") in {"allowed_fallback", "write_external_fallback", "diagnostic_only"}]
    for row in retired_rows:
        if _row_expected_bool(row) is not False:
            blockers.append(
                {
                    "reason": "retired_route_expected_true",
                    "route_or_pattern": row.get("route_or_pattern"),
                    "legacy_registration_expected": row.get("legacy_registration_expected"),
                }
            )
    for row in allowed_rows:
        if _row_expected_bool(row) is not True:
            blockers.append(
                {
                    "reason": "allowed_fallback_expected_not_true",
                    "route_or_pattern": row.get("route_or_pattern"),
                    "legacy_registration_expected": row.get("legacy_registration_expected"),
                }
            )
    matrix_text = "\n".join(str(row.get("route_or_pattern", "")) for row in retired_rows)
    missing_groups: dict[str, list[str]] = {}
    for group, terms in REQUIRED_RETIRED_GROUP_TERMS.items():
        missing = [term for term in terms if term not in matrix_text]
        if missing:
            missing_groups[group] = missing
            blockers.append({"reason": "retired_route_group_missing", "group": group, "missing_terms": missing})
    return retired_rows, allowed_rows, {"missing_groups": missing_groups, "required_groups_present": not missing_groups}


def _check_retired_registration(rows: list[Json], route_map: list[Json], blockers: list[Json]) -> list[Json]:
    retired_registered: list[Json] = []
    for row in rows:
        if row.get("category") != "retired_readonly_route":
            continue
        for route in route_map:
            if _matches_row(row, route):
                item = {
                    "route_or_pattern": row.get("route_or_pattern"),
                    "method": row.get("method"),
                    "registered_path": route["path"],
                    "registered_method": route["method"],
                    "source": route["source"],
                }
                retired_registered.append(item)
                blockers.append({"reason": "retired_readonly_route_still_registered", **item})
    return retired_registered


def _check_default_runtime(blockers: list[Json]) -> Json:
    source = _read("app.py") if _path("app.py").exists() else ""
    default_next = (
        'NEXT_APP_IMPORT = "aicrm_next.main:app"' in source
        and 'command = args.command or "run"' in source
        and "run_next()" in source
    )
    if not default_next:
        blockers.append({"reason": "app_py_default_not_next"})
    return {"default_runtime": "ai_crm_next" if default_next else "unknown"}


def _check_shell_presence(blockers: list[Json]) -> Json:
    required = {
        "legacy_flask_app.py": _path("legacy_flask_app.py").exists(),
        "wecom_ability_service": _path("wecom_ability_service").exists(),
        "wecom_ability_service/http/__init__.py": _path("wecom_ability_service/http/__init__.py").exists(),
        "openclaw_service": _path("openclaw_service").exists(),
    }
    for path, exists in required.items():
        if not exists:
            blockers.append({"reason": "missing_legacy_fallback_component", "path": path})
    return required


def _changed_paths() -> list[str]:
    completed = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=PROJECT_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    paths: list[str] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        paths.append(path)
    return paths


def _is_production_config_path(path: str) -> bool:
    lowered = path.lower()
    return (
        lowered.startswith("deploy/")
        or lowered == ".github/workflows/deploy.yml"
        or "nginx" in lowered
        or "systemd" in lowered
        or lowered.endswith(".service")
        or lowered.endswith(".timer")
    )


def _check_production_config_modified(blockers: list[Json]) -> Json:
    modified = [path for path in _changed_paths() if _is_production_config_path(path)]
    if modified:
        blockers.append({"reason": "production_config_modified", "paths": modified})
    return {"production_config_modified": bool(modified), "modified_paths": modified}


def _check_forbidden_markers(blockers: list[Json]) -> list[Json]:
    findings: list[Json] = []
    for relpath in DOCS_TO_SCAN:
        path = _path(relpath)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_STATUS_MARKERS:
            if marker in text:
                item = {"path": relpath, "marker": marker}
                findings.append(item)
                blockers.append({"reason": "forbidden_status_marker", **item})
    return findings


def run_check(matrix_path: str = "docs/d8_1_legacy_fallback_route_matrix.md") -> Json:
    blockers: list[Json] = []
    warnings: list[Json] = []
    matrix = _path(matrix_path) if not Path(matrix_path).is_absolute() else Path(matrix_path)
    if not matrix.exists():
        blockers.append({"reason": "missing_route_matrix", "path": str(matrix)})
        rows: list[Json] = []
    else:
        rows = parse_matrix(matrix)
    if not _path("docs/d8_1_legacy_fallback_route_lockdown_plan.md").exists():
        blockers.append({"reason": "missing_lockdown_plan"})
    if not _path("tools/check_d8_1_legacy_fallback_route_lockdown.py").exists():
        blockers.append({"reason": "missing_lockdown_checker"})
    route_map = build_static_legacy_route_map()
    if not route_map:
        blockers.append({"reason": "legacy_route_map_unavailable"})
    retired_rows, allowed_rows, group_coverage = _check_matrix(rows, blockers)
    retired_registered = _check_retired_registration(retired_rows, route_map, blockers)
    default_runtime = _check_default_runtime(blockers)
    shell_presence = _check_shell_presence(blockers)
    production_config = _check_production_config_modified(blockers)
    forbidden_status_markers = _check_forbidden_markers(blockers)
    if not blockers:
        warnings.append(
            {
                "reason": "planning_only",
                "message": "D8.1 is route-lockdown planning only; no runtime enforcement or production cutover is applied.",
            }
        )
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "retired_routes_checked": [
            {
                "route_or_pattern": row.get("route_or_pattern"),
                "method": row.get("method"),
                "legacy_registration_expected": row.get("legacy_registration_expected"),
            }
            for row in retired_rows
        ],
        "retired_routes_still_registered": retired_registered,
        "allowed_fallback_routes": [
            {
                "route_or_pattern": row.get("route_or_pattern"),
                "method": row.get("method"),
                "category": row.get("category"),
            }
            for row in allowed_rows
        ],
        "legacy_route_map_available": bool(route_map),
        "legacy_route_map_count": len(route_map),
        "required_retired_groups": group_coverage,
        "default_runtime": default_runtime,
        "legacy_shell_presence": shell_presence,
        "production_config_modified": production_config["production_config_modified"],
        "production_config": production_config,
        "forbidden_status_markers": forbidden_status_markers,
        "recommendation": (
            "READY_FOR_D8_1_LOCKDOWN_PLANNING_ACCEPTANCE_NOT_ENFORCED"
            if not blockers
            else "FIX_D8_1_LOCKDOWN_PLANNING_BLOCKERS_BEFORE_ACCEPTANCE"
        ),
    }


def _write_markdown(path: str, result: Json) -> None:
    lines = [
        "# D8.1 Legacy Fallback Route Lockdown Check",
        "",
        f"- ok: `{str(result['ok']).lower()}`",
        f"- blockers: `{len(result['blockers'])}`",
        f"- warnings: `{len(result['warnings'])}`",
        f"- retired routes checked: `{len(result['retired_routes_checked'])}`",
        f"- retired routes still registered: `{len(result['retired_routes_still_registered'])}`",
        f"- allowed fallback routes: `{len(result['allowed_fallback_routes'])}`",
        f"- legacy route map available: `{str(result['legacy_route_map_available']).lower()}`",
        f"- production config modified: `{str(result['production_config_modified']).lower()}`",
        f"- recommendation: `{result['recommendation']}`",
        "",
        "## Blockers",
    ]
    if result["blockers"]:
        lines.extend(f"- `{item}`" for item in result["blockers"])
    else:
        lines.append("- none")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check D8.1 legacy fallback route lockdown planning readiness.")
    parser.add_argument("--matrix", default="docs/d8_1_legacy_fallback_route_matrix.md")
    parser.add_argument("--output-md", default="")
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()
    result = run_check(args.matrix)
    if args.output_md:
        _write_markdown(args.output_md, result)
        print(f"wrote markdown report: {args.output_md}")
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote json report: {args.output_json}")
    print(f"overall: {'PASS' if result['ok'] else 'FAIL'}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
