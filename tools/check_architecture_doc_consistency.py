from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

SCANNED_DOCS = [
    "README.md",
    "docs/project_map.md",
    "docs/llm_handoff.md",
    "docs/module_status_matrix.md",
]

ENTRY_DOCS = [
    "README.md",
    "docs/project_map.md",
    "docs/llm_handoff.md",
]

RUNTIME_REQUIRED = [
    "AI-CRM Next FastAPI",
    "app.py run",
    "aicrm_next.main:app",
    "legacy fallback",
    "wecom_ability_service/",
]

D96_REQUIRED = [
    "D9.6",
    "openclaw_service/",
    "legacy_flask/openclaw_legacy/",
    "physically removed",
    "aicrm_next.integration_gateway",
]

LLM_FORBIDDEN_READ_PATTERNS = [
    re.compile(r"(?:read|读|进入|查看|scan|扫).{0,80}`?openclaw_service/?`?", re.IGNORECASE),
    re.compile(r"\.\./openclaw_service", re.IGNORECASE),
]

LIVE_SOURCE_PATTERNS = [
    re.compile(r"├── openclaw_service/"),
    re.compile(r"## `openclaw_service/`"),
    re.compile(r"\[`openclaw_service/[^`]*`\]\(\.\./openclaw_service", re.IGNORECASE),
]

ALLOWED_OPENCLAW_CONTEXT = [
    "not a live repo path",
    "不是 live repo path",
    "physically removed",
    "物理删除",
    "absent",
    "已删除",
    "deleted",
    "must not be reintroduced",
    "不得重新引入",
    "historical",
    "历史",
    "D9.6",
    "blocked",
    "禁止新增",
]


def _read(root: Path, relpath: str) -> str:
    return (root / relpath).read_text(encoding="utf-8")


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _openclaw_mentions_are_historical(text: str) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for match in re.finditer(r"openclaw_service/", text, flags=re.IGNORECASE):
        start = max(0, match.start() - 140)
        end = min(len(text), match.end() + 180)
        context = text[start:end]
        if not any(marker.lower() in context.lower() for marker in ALLOWED_OPENCLAW_CONTEXT):
            violations.append(
                {
                    "line": _line_number(text, match.start()),
                    "context": " ".join(context.split()),
                }
            )
    return violations


def _pattern_hits(text: str, patterns: list[re.Pattern[str]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            hits.append(
                {
                    "line": _line_number(text, match.start()),
                    "pattern": pattern.pattern,
                    "match": match.group(0),
                }
            )
    return hits


def build_report(root: Path = REPO_ROOT) -> dict[str, Any]:
    blockers: list[str] = []
    docs: dict[str, str] = {}
    doc_presence: dict[str, bool] = {}

    for relpath in SCANNED_DOCS:
        exists = (root / relpath).exists()
        doc_presence[relpath] = exists
        if not exists:
            blockers.append(f"missing scanned doc: {relpath}")
            continue
        docs[relpath] = _read(root, relpath)

    openclaw_live_source_violations: dict[str, list[dict[str, Any]]] = {}
    for relpath in ENTRY_DOCS:
        text = docs.get(relpath, "")
        violations = _pattern_hits(text, LIVE_SOURCE_PATTERNS) + _openclaw_mentions_are_historical(text)
        if violations:
            openclaw_live_source_violations[relpath] = violations
            blockers.append(f"{relpath} describes openclaw_service/ as a current live source path")

    llm_handoff_openclaw_read_suggestion = _pattern_hits(
        docs.get("docs/llm_handoff.md", ""),
        LLM_FORBIDDEN_READ_PATTERNS,
    )
    if llm_handoff_openclaw_read_suggestion:
        blockers.append("docs/llm_handoff.md still suggests reading openclaw_service/ as current code")

    runtime_consistency = {
        "README.md": {phrase: phrase in docs.get("README.md", "") for phrase in RUNTIME_REQUIRED + D96_REQUIRED},
        "docs/project_map.md": {
            phrase: phrase in docs.get("docs/project_map.md", "") for phrase in RUNTIME_REQUIRED + D96_REQUIRED
        },
    }
    for relpath, phrase_map in runtime_consistency.items():
        for phrase, present in phrase_map.items():
            if not present:
                blockers.append(f"{relpath} missing architecture status phrase: {phrase}")

    skill_doc = root / "docs/development/ai_crm_next_architecture_skill.md"
    template_doc = root / "docs/development/codex_task_template.md"
    development_docs = {
        "docs/development/ai_crm_next_architecture_skill.md": skill_doc.exists(),
        "docs/development/codex_task_template.md": template_doc.exists(),
    }
    for relpath, exists in development_docs.items():
        if not exists:
            blockers.append(f"missing development doc: {relpath}")

    return {
        "ok": not blockers,
        "blockers": blockers,
        "checks": {
            "doc_presence": doc_presence,
            "development_docs": development_docs,
            "openclaw_live_source_violations": openclaw_live_source_violations,
            "llm_handoff_openclaw_read_suggestion": llm_handoff_openclaw_read_suggestion,
            "runtime_consistency": runtime_consistency,
        },
    }


def _write_json(path: str, report: dict[str, Any]) -> None:
    if not path:
        return
    Path(path).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_markdown(path: str, report: dict[str, Any]) -> None:
    if not path:
        return
    lines = [
        "# Architecture Doc Consistency",
        "",
        f"overall: {'PASS' if report['ok'] else 'FAIL'}",
        "",
        "## Checks",
    ]
    for name, value in report["checks"].items():
        lines.append(f"- {name}: `{value}`")
    if report["blockers"]:
        lines.extend(["", "## Blockers"])
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check architecture docs for AI-CRM Next status consistency.")
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
