from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
D8_1_DOCS = [
    "docs/d8_1_legacy_fallback_route_lockdown_plan.md",
    "docs/d8_1_legacy_fallback_route_matrix.md",
]
REQUIRED_CATEGORIES = [
    "Payment checkout/notify/admin",
    "Questionnaire submit/OAuth/write/external push",
    "User Ops write/WeCom dispatch/deferred jobs",
    "Automation write/webhook/runtime/agent/OpenClaw",
    "Archive/contacts/identity",
    "Media cloud/WeCom upload",
    "MCP/OpenClaw adapter",
    "Legacy shell entry",
]
FORBIDDEN_MARKERS = ("delete" + "_ready", "production" + "_ready", "production" + "_approved")


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
        "# D8.1 Legacy Fallback Route Lockdown Planning",
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

    doc_presence = {path: (REPO_ROOT / path).exists() for path in D8_1_DOCS}
    for path, exists in doc_presence.items():
        if not exists:
            blockers.append(f"missing D8.1 planning doc: {path}")

    docs_text = "\n".join(_read(path) for path in D8_1_DOCS if (REPO_ROOT / path).exists())
    forbidden_markers: list[str] = []
    for marker in FORBIDDEN_MARKERS:
        if marker in docs_text:
            forbidden_markers.append(marker)
            blockers.append(f"forbidden readiness marker in D8.1 docs: {marker}")

    planning_only = "planning/readiness only" in docs_text
    no_runtime_enforcement = (
        "does not register runtime enforcement" in docs_text
        and "does not change route behavior" in docs_text
        and "No runtime guard is registered" in docs_text
    )
    if not planning_only:
        blockers.append("D8.1 docs do not state planning/readiness only")
    if not no_runtime_enforcement:
        blockers.append("D8.1 docs do not clearly block runtime enforcement")

    category_presence = {category: category in docs_text for category in REQUIRED_CATEGORIES}
    for category, present in category_presence.items():
        if not present:
            blockers.append(f"D8.1 matrix missing category: {category}")

    runtime_guard_absent = not (REPO_ROOT / "wecom_ability_service" / "legacy_lockdown.py").exists()
    archive_package_absent = not (REPO_ROOT / "legacy_flask").exists()
    if not runtime_guard_absent:
        blockers.append("runtime lockdown shim unexpectedly exists")
    if not archive_package_absent:
        blockers.append("legacy_flask archive package unexpectedly exists")

    protected_paths = {
        "legacy_flask_app.py": (REPO_ROOT / "legacy_flask_app.py").exists(),
        "wecom_ability_service": (REPO_ROOT / "wecom_ability_service").exists(),
        "openclaw_service_absent_after_d9_6": not (REPO_ROOT / "openclaw_service").exists(),
    }
    for path, exists in protected_paths.items():
        if not exists:
            blockers.append(f"D8/D9 fallback status mismatch: {path}")

    return {
        "ok": not blockers,
        "blockers": blockers,
        "checks": {
            "doc_presence": doc_presence,
            "forbidden_markers": forbidden_markers,
            "planning_only": planning_only,
            "no_runtime_enforcement": no_runtime_enforcement,
            "category_presence": category_presence,
            "runtime_guard_absent": runtime_guard_absent,
            "archive_package_absent": archive_package_absent,
            "protected_paths": protected_paths,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check D8.1 fallback route lockdown planning readiness.")
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
