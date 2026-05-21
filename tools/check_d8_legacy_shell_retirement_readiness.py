from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
D8_DOCS = [
    "docs/d8_legacy_flask_shell_retirement_plan.md",
    "docs/d8_legacy_shell_dependency_inventory.md",
    "docs/d8_legacy_shell_allowed_fallback_matrix.md",
]
PROTECTED_PATHS = [
    "app.py",
    "legacy_flask_app.py",
    "wecom_ability_service",
    "wecom_ability_service/__init__.py",
    "wecom_ability_service/routes.py",
    "wecom_ability_service/http/__init__.py",
    "openclaw_service",
]
ABSENT_RUNTIME_PATHS = [
    "legacy_flask",
    "wecom_ability_service/legacy_lockdown.py",
]
FORBIDDEN_MARKERS = ("delete" + "_ready", "production" + "_ready", "production" + "_approved")
DELETE_GATE_ITEMS = [
    "D7 real external replacement evidence",
    "Production observation window",
    "No legacy route hits",
    "Rollback no longer requires Flask shell",
    "Deploy/systemd Next-only path",
    "Human signoff",
]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _write_json(path: str, report: dict[str, Any]) -> None:
    if not path:
        return
    Path(path).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_markdown(path: str, report: dict[str, Any]) -> None:
    if not path:
        return
    lines = [
        "# D8 Legacy Shell Retirement Readiness",
        "",
        f"overall: {'PASS' if report['ok'] else 'FAIL'}",
        "",
        "## Checks",
    ]
    for name, value in report["checks"].items():
        lines.append(f"- {name}: {value}")
    if report["blockers"]:
        lines.extend(["", "## Blockers"])
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report() -> dict[str, Any]:
    blockers: list[str] = []

    doc_presence = {path: (REPO_ROOT / path).exists() for path in D8_DOCS}
    for path, exists in doc_presence.items():
        if not exists:
            blockers.append(f"missing D8.0 planning doc: {path}")

    docs_text = "\n".join(_read(path) for path in D8_DOCS if (REPO_ROOT / path).exists())
    forbidden_markers: list[str] = []
    for marker in FORBIDDEN_MARKERS:
        if marker in docs_text:
            forbidden_markers.append(marker)
            blockers.append(f"forbidden readiness marker in D8.0 docs: {marker}")

    planning_only = "planning/readiness only" in docs_text
    if not planning_only:
        blockers.append("D8.0 docs do not state planning/readiness only")

    non_goals = all(
        phrase in docs_text
        for phrase in [
            "No D8 shell deletion",
            "No D8.2-D8.5 work",
            "No `legacy_flask/` package creation",
            "No runtime route lockdown implementation",
        ]
    )
    if not non_goals:
        blockers.append("D8.0 non-goals are incomplete")

    delete_gate = {item: item in docs_text for item in DELETE_GATE_ITEMS}
    for item, present in delete_gate.items():
        if not present:
            blockers.append(f"D8.0 deletion gate missing: {item}")

    protected_paths = {path: (REPO_ROOT / path).exists() for path in PROTECTED_PATHS}
    for path, exists in protected_paths.items():
        if not exists:
            blockers.append(f"protected fallback path missing: {path}")

    absent_runtime_paths = {path: not (REPO_ROOT / path).exists() for path in ABSENT_RUNTIME_PATHS}
    for path, absent in absent_runtime_paths.items():
        if not absent:
            blockers.append(f"D8 runtime/archive path unexpectedly exists: {path}")

    app_text = _read("app.py")
    legacy_text = _read("legacy_flask_app.py")
    default_next_runtime = "Default runtime is AI-CRM Next" in app_text and "run_next()" in app_text
    explicit_fallback = "run-legacy" in app_text and "Explicit legacy Flask fallback runner" in legacy_text
    if not default_next_runtime:
        blockers.append("app.py no longer clearly keeps AI-CRM Next as default runtime")
    if not explicit_fallback:
        blockers.append("legacy fallback is no longer clearly explicit")

    return {
        "ok": not blockers,
        "blockers": blockers,
        "checks": {
            "doc_presence": doc_presence,
            "forbidden_markers": forbidden_markers,
            "planning_only": planning_only,
            "non_goals": non_goals,
            "delete_gate": delete_gate,
            "protected_paths": protected_paths,
            "absent_runtime_paths": absent_runtime_paths,
            "default_next_runtime": default_next_runtime,
            "explicit_fallback": explicit_fallback,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check D8.0 legacy shell retirement planning readiness.")
    parser.add_argument("--output-md", default="")
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()

    report = build_report()
    _write_markdown(args.output_md, report)
    _write_json(args.output_json, report)
    print(f"overall: {'PASS' if report['ok'] else 'FAIL'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
