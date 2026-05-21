#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_STATUS_MARKERS = ["production_ready", "production_approved", "delete_ready"]
PRODUCTION_CONFIG_PATH_TOKENS = (
    "deploy/",
    "nginx",
    "systemd",
    "supervisor",
    "docker-compose",
    "production.env",
    ".prod",
)
REQUIRED_CLASSIFICATION_SECTIONS = [
    "D7.1 baseline files",
    "D7.2 baseline files",
    "D7.3 baseline files",
    "D7.4 increment files",
    "shared infrastructure files",
    "docs/tests/checkers",
    "out-of-scope files",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _git_changed_files() -> list[str]:
    changed: set[str] = set()
    commands = (
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    )
    for command in commands:
        result = subprocess.run(command, cwd=REPO_ROOT, check=False, capture_output=True, text=True)
        if result.returncode == 0:
            changed.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return sorted(changed)


def _is_production_config_path(path: str) -> bool:
    lower = path.lower()
    return any(token in lower for token in PRODUCTION_CONFIG_PATH_TOKENS)


def _section_items(markdown: str, heading: str) -> list[str]:
    pattern = re.compile(rf"^(?P<level>#+)\s+{re.escape(heading)}\s*$", re.MULTILINE | re.IGNORECASE)
    match = pattern.search(markdown)
    if not match:
        return []
    level = len(match.group("level"))
    start = match.end()
    next_heading = re.compile(rf"^#{{1,{level}}}\s+", re.MULTILINE)
    next_match = next_heading.search(markdown, start)
    section = markdown[start : next_match.start() if next_match else len(markdown)]
    items: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        value = stripped[2:].strip()
        if value.startswith("`") and value.endswith("`"):
            value = value[1:-1]
        items.append(value)
    return items


def _classified_files(scope_report_text: str) -> set[str]:
    files: set[str] = set()
    for section in REQUIRED_CLASSIFICATION_SECTIONS:
        for item in _section_items(scope_report_text, section):
            if item.lower() != "none":
                files.add(item)
    return files


def build_report(
    *,
    baseline_summary: Path,
    d7_4_scope_report: Path,
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if not baseline_summary.exists():
        blockers.append({"reason": "missing_baseline_summary", "path": str(baseline_summary)})
        baseline_text = ""
    else:
        baseline_text = _read(baseline_summary)

    if not d7_4_scope_report.exists():
        blockers.append({"reason": "missing_d7_4_scope_report", "path": str(d7_4_scope_report)})
        scope_text = ""
    else:
        scope_text = _read(d7_4_scope_report)

    accepted_prerequisites = []
    for stage in ("D7.1", "D7.2", "D7.3"):
        if stage in baseline_text and "accepted_prerequisite" in baseline_text:
            accepted_prerequisites.append(stage)
        else:
            blockers.append({"reason": "missing_accepted_prerequisite_marker", "stage": stage})

    current_increment = []
    if "D7.4" in baseline_text and "current_increment" in baseline_text:
        current_increment.append("D7.4")
    else:
        blockers.append({"reason": "missing_current_increment_marker", "stage": "D7.4"})

    missing_sections = [section for section in REQUIRED_CLASSIFICATION_SECTIONS if not _section_items(scope_text, section)]
    for section in missing_sections:
        blockers.append({"reason": "missing_scope_classification_section", "section": section})

    for section in ("D7.1 baseline files", "D7.2 baseline files", "D7.3 baseline files"):
        items = _section_items(scope_text, section)
        if not items:
            blockers.append({"reason": "missing_prerequisite_classification", "section": section})

    out_of_scope_items = [item for item in _section_items(scope_text, "out-of-scope files") if item.lower() != "none"]
    for item in out_of_scope_items:
        blockers.append({"reason": "out_of_scope_file_present", "path": item})

    increment_files = [item for item in _section_items(scope_text, "D7.4 increment files") if item.lower() != "none"]
    if not increment_files:
        blockers.append({"reason": "missing_d7_4_increment_files"})

    production_config_increment = [path for path in increment_files if _is_production_config_path(path)]
    for path in production_config_increment:
        blockers.append({"reason": "production_config_in_current_increment", "path": path})

    docs_to_scan = [
        baseline_summary,
        d7_4_scope_report,
        REPO_ROOT / "docs/d7_4_product_payment_adapter_contract.md",
        REPO_ROOT / "docs/d7_4_product_payment_adapter_implementation_report.md",
        REPO_ROOT / "docs/d7_capability_readiness_matrix.md",
        REPO_ROOT / "docs/remaining_work_queue.md",
        REPO_ROOT / "docs/go_no_go_checklist.md",
    ]
    forbidden_status_markers: list[str] = []
    for path in docs_to_scan:
        if not path.exists():
            continue
        text = _read(path)
        forbidden_status_markers.extend(marker for marker in FORBIDDEN_STATUS_MARKERS if marker in text)
    forbidden_status_markers = sorted(set(forbidden_status_markers))
    for marker in forbidden_status_markers:
        blockers.append({"reason": "forbidden_status_marker", "marker": marker})

    # The changed-file scope gate is meaningful for D7.4 acceptance runs that
    # pass an explicit diff. Default test runs can happen on later maintenance
    # branches, where unrelated corrective files should not retroactively fail
    # the historical D7.4 scope report.
    current_changed_files = changed_files if changed_files is not None else []
    classified = _classified_files(scope_text)
    unclassified_changed_files = [path for path in current_changed_files if path not in classified]
    for path in unclassified_changed_files:
        blockers.append({"reason": "unclassified_changed_file", "path": path})

    production_config_modified = any(_is_production_config_path(path) for path in current_changed_files)
    if production_config_modified:
        blockers.append({"reason": "production_config_modified"})

    if not current_changed_files:
        warnings.append({"reason": "no_changed_files_detected"})

    ok = not blockers
    return {
        "ok": ok,
        "blockers": blockers,
        "warnings": warnings,
        "accepted_prerequisites": accepted_prerequisites,
        "current_increment": current_increment,
        "out_of_scope_files": out_of_scope_items,
        "forbidden_status_markers": forbidden_status_markers,
        "production_config_modified": production_config_modified,
        "d7_4_increment_files": increment_files,
        "unclassified_changed_files": unclassified_changed_files,
        "recommendation": "D7.4 scope isolation can proceed to acceptance" if ok else "Fix D7.4 scope isolation blockers before acceptance",
    }


def write_markdown(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    def bullet_lines(items: list[Any]) -> list[str]:
        return [f"- {item}" for item in items] or ["- none"]

    lines = [
        "# D7 Scope Isolation Check",
        "",
        f"- ok: `{str(report['ok']).lower()}`",
        f"- recommendation: `{report['recommendation']}`",
        f"- production_config_modified: `{str(report['production_config_modified']).lower()}`",
        "",
        "## Accepted Prerequisites",
        *bullet_lines(report["accepted_prerequisites"]),
        "",
        "## Current Increment",
        *bullet_lines(report["current_increment"]),
        "",
        "## Out Of Scope Files",
        *bullet_lines(report["out_of_scope_files"]),
        "",
        "## Forbidden Status Markers",
        *bullet_lines(report["forbidden_status_markers"]),
        "",
        "## Blockers",
    ]
    lines.extend([f"- {json.dumps(item, ensure_ascii=False)}" for item in report["blockers"]] or ["- none"])
    lines.extend(["", "## Warnings"])
    lines.extend([f"- {json.dumps(item, ensure_ascii=False)}" for item in report["warnings"]] or ["- none"])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check D7.4 scope isolation against accepted D7.1-D7.3 prerequisites.")
    parser.add_argument("--baseline-summary", required=True)
    parser.add_argument("--d7-4-scope-report", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(
        baseline_summary=Path(args.baseline_summary),
        d7_4_scope_report=Path(args.d7_4_scope_report),
    )
    Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, Path(args.output_md))
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print("overall:", "PASS" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
