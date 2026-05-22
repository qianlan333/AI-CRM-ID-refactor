from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

D8_0_REQUIRED = [
    "docs/d8_legacy_flask_shell_retirement_plan.md",
    "docs/d8_legacy_shell_dependency_inventory.md",
    "docs/d8_legacy_shell_allowed_fallback_matrix.md",
    "tools/check_d8_legacy_shell_retirement_readiness.py",
    "tests/test_d8_legacy_shell_retirement_readiness.py",
]
D8_1_REQUIRED = [
    "docs/d8_1_legacy_fallback_route_lockdown_plan.md",
    "docs/d8_1_legacy_fallback_route_matrix.md",
    "tools/check_d8_1_legacy_fallback_route_lockdown.py",
    "tests/test_d8_1_legacy_fallback_route_lockdown.py",
]
D8_2_ALLOWED = [
    "docs/d8_2_legacy_fallback_route_lockdown_preflight.md",
    "tools/check_d8_2_legacy_lockdown_preflight.py",
    "tests/test_d8_2_legacy_lockdown_preflight.py",
]
D8_2_RUNTIME_FORBIDDEN = [
    "openclaw_service",
    "legacy_flask",
    "wecom_ability_service/legacy_lockdown.py",
    "docs/d8_2_legacy_fallback_route_lockdown_enforcement.md",
    "docs/d8_2_legacy_fallback_route_lockdown_report.md",
    "tools/check_d8_2_legacy_lockdown_enforcement.py",
    "tests/test_d8_2_legacy_lockdown_enforcement.py",
]
D8_LATER_FORBIDDEN = [
    "docs/d8_3_legacy_flask_shell_archive_package_plan.md",
    "docs/d8_3_legacy_package_move_map.md",
    "docs/d8_3_legacy_import_rewrite_plan.md",
    "docs/d8_4_legacy_flask_archive_package_implementation.md",
    "docs/d8_4_legacy_flask_archive_package_report.md",
    "docs/d8_5_legacy_db_maintenance_command_inventory.md",
    "docs/d8_5_legacy_db_maintenance_command_retirement_plan.md",
    "docs/d8_5_maintenance_command_replacement_matrix.md",
    "tools/check_d8_3_legacy_archive_move_readiness.py",
    "tools/check_d8_4_legacy_archive_package.py",
    "tools/check_d8_5_legacy_maintenance_command_readiness.py",
    "tests/test_d8_3_legacy_archive_move_readiness.py",
    "tests/test_d8_4_legacy_archive_package.py",
    "tests/test_d8_5_legacy_maintenance_command_readiness.py",
]
RETIRED_READONLY_ROUTES = [
    "D1 Media old readonly routes",
    "D2 Product old readonly routes",
    "D3 Customer old readonly routes",
    "D4 User Ops old readonly routes",
    "D5 Questionnaire old readonly routes",
    "D6 Automation old readonly routes",
]
ALLOWED_FALLBACK_COVERAGE = {
    "payment": ["Payment checkout", "payment"],
    "OAuth": ["OAuth"],
    "questionnaire submit": ["Questionnaire submit"],
    "archive": ["Archive"],
    "contacts": ["contacts"],
    "identity": ["identity"],
    "automation": ["Automation"],
    "OpenClaw": ["OpenClaw"],
    "operational diagnostics": ["operational diagnostics"],
}
FORBIDDEN_MARKERS = ("delete" + "_ready", "production" + "_ready", "production" + "_approved")
PRODUCTION_CONFIG_PREFIXES = ("production/", "deploy/", "nginx/", "systemd/")


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _exists(path: str) -> bool:
    return (REPO_ROOT / path).exists()


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=REPO_ROOT, text=True, capture_output=True, check=False)


def _changed_files() -> list[str]:
    result = _run(["git", "status", "--short", "--untracked-files=all"])
    if result.returncode != 0:
        return []
    names: set[str] = set()
    for line in result.stdout.splitlines():
        name = line[3:]
        if " -> " in name:
            name = name.split(" -> ", 1)[1]
        if name:
            names.add(name)
    return sorted(names)


def _write_json(path: str, report: dict[str, Any]) -> None:
    if path:
        Path(path).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_markdown(path: str, report: dict[str, Any]) -> None:
    if not path:
        return
    lines = [
        "# D8.2 Legacy Lockdown Preflight",
        "",
        f"overall: {'PASS' if report['ok'] else 'FAIL'}",
        f"ready_for_enforcement: {report['ready_for_enforcement']}",
        "",
        "## Hard Failures",
    ]
    lines.extend(f"- {item}" for item in report["hard_failures"]) or lines.append("- none")
    lines.extend(["", "## Readiness Blockers"])
    lines.extend(f"- {item}" for item in report["readiness_blockers"]) or lines.append("- none")
    lines.extend(["", "## Checks"])
    for name, value in report["checks"].items():
        lines.append(f"- {name}: {value}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report() -> dict[str, Any]:
    hard_failures: list[str] = []
    readiness_blockers: list[str] = []

    d8_0_presence = {path: _exists(path) for path in D8_0_REQUIRED}
    d8_1_presence = {path: _exists(path) for path in D8_1_REQUIRED}
    for path, exists in {**d8_0_presence, **d8_1_presence}.items():
        if not exists:
            hard_failures.append(f"missing planning prerequisite: {path}")

    d8_2_runtime_absent = {path: not _exists(path) for path in D8_2_RUNTIME_FORBIDDEN}
    d8_later_absent = {path: not _exists(path) for path in D8_LATER_FORBIDDEN}
    for path, absent in {**d8_2_runtime_absent, **d8_later_absent}.items():
        if not absent:
            hard_failures.append(f"forbidden D8 runtime/later-phase artifact exists: {path}")

    matrix_text = _read("docs/d8_1_legacy_fallback_route_matrix.md") if _exists("docs/d8_1_legacy_fallback_route_matrix.md") else ""
    allowed_text = (
        _read("docs/d8_legacy_shell_allowed_fallback_matrix.md")
        if _exists("docs/d8_legacy_shell_allowed_fallback_matrix.md")
        else ""
    )
    retired_readonly_coverage = {route: route in matrix_text for route in RETIRED_READONLY_ROUTES}
    for route, present in retired_readonly_coverage.items():
        if not present:
            readiness_blockers.append(f"D8.1 matrix missing retired readonly route coverage: {route}")

    allowed_fallback_coverage = {
        name: all(token in allowed_text for token in tokens) for name, tokens in ALLOWED_FALLBACK_COVERAGE.items()
    }
    for name, present in allowed_fallback_coverage.items():
        if not present:
            readiness_blockers.append(f"allowed fallback matrix missing coverage: {name}")

    retired_allowed_conflicts: list[str] = []
    for route in RETIRED_READONLY_ROUTES:
        if route in allowed_text:
            retired_allowed_conflicts.append(route)
            readiness_blockers.append(f"retired readonly route conflicts with allowed fallback matrix: {route}")

    app_text = _read("app.py")
    legacy_text = _read("legacy_flask_app.py")
    default_next_runtime = "Default runtime is AI-CRM Next" in app_text and "run_next()" in app_text
    explicit_fallback = "run-legacy" in app_text and "Explicit legacy Flask fallback runner" in legacy_text
    if not default_next_runtime:
        hard_failures.append("default runtime no longer clearly points to AI-CRM Next")
    if not explicit_fallback:
        hard_failures.append("legacy fallback is no longer explicit-only")

    legacy_help = _run([sys.executable, "legacy_flask_app.py", "--help"])
    legacy_import = _run([sys.executable, "-c", "from legacy_flask_app import main; print('legacy fallback import ok')"])
    legacy_help_ok = legacy_help.returncode == 0 and "Explicit legacy Flask fallback runner" in legacy_help.stdout
    legacy_import_ok = legacy_import.returncode == 0 and "legacy fallback import ok" in legacy_import.stdout
    if not legacy_help_ok:
        hard_failures.append("legacy_flask_app.py help failed")
    if not legacy_import_ok:
        hard_failures.append("legacy fallback import failed")

    d8_docs = sorted((REPO_ROOT / "docs").glob("d8_*.md"))
    forbidden_markers: list[str] = []
    for path in d8_docs:
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_MARKERS:
            if marker in text:
                forbidden_markers.append(f"{path.relative_to(REPO_ROOT)}:{marker}")
    if forbidden_markers:
        hard_failures.extend(f"forbidden readiness/status marker present: {item}" for item in forbidden_markers)

    changed_files = _changed_files()
    production_config_changes = [
        path for path in changed_files if path.startswith(PRODUCTION_CONFIG_PREFIXES) or path in {"nginx.conf", "systemd.conf"}
    ]
    if production_config_changes:
        hard_failures.extend(f"production/deploy config changed: {path}" for path in production_config_changes)

    return {
        "ok": not hard_failures,
        "ready_for_enforcement": not hard_failures and not readiness_blockers,
        "hard_failures": hard_failures,
        "readiness_blockers": readiness_blockers,
        "checks": {
            "d8_0_presence": d8_0_presence,
            "d8_1_presence": d8_1_presence,
            "d8_2_runtime_absent": d8_2_runtime_absent,
            "d8_later_absent": d8_later_absent,
            "retired_readonly_coverage": retired_readonly_coverage,
            "allowed_fallback_coverage": allowed_fallback_coverage,
            "retired_allowed_conflicts": retired_allowed_conflicts,
            "default_next_runtime": default_next_runtime,
            "explicit_fallback": explicit_fallback,
            "legacy_help_ok": legacy_help_ok,
            "legacy_import_ok": legacy_import_ok,
            "forbidden_markers": forbidden_markers,
            "production_config_changes": production_config_changes,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check D8.2 legacy fallback route lockdown preflight.")
    parser.add_argument("--output-md", default="")
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()

    report = build_report()
    _write_markdown(args.output_md, report)
    _write_json(args.output_json, report)
    print(f"overall: {'PASS' if report['ok'] else 'FAIL'}")
    print(f"ready_for_enforcement: {report['ready_for_enforcement']}")
    if report["readiness_blockers"]:
        print(f"readiness_blockers: {len(report['readiness_blockers'])}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
