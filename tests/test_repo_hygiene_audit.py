from __future__ import annotations

import json
from pathlib import Path

from tools.audit_repo_hygiene import audit_repository, render_human_summary, write_report_files


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _findings_by_category(report, category: str):
    return [finding for finding in report.findings if finding.category == category]


def test_audit_reports_missing_markdown_references_from_agent_docs(tmp_path) -> None:
    _write(tmp_path / "AGENTS.md", "Read [skill](docs/development/ai_crm_next_architecture_skill.md).\n")
    _write(tmp_path / "docs/development/ai_crm_next_architecture_skill.md", "# Skill\n")
    _write(
        tmp_path / "skills/ai-crm-next-architecture/SKILL.md",
        "Read `docs/development/codex_architecture_operating_memory.md` first.\n",
    )

    report = audit_repository(tmp_path)

    missing = _findings_by_category(report, "missing_markdown_reference")
    assert len(missing) == 1
    assert missing[0].path == "skills/ai-crm-next-architecture/SKILL.md"
    assert "codex_architecture_operating_memory.md" in missing[0].detail


def test_audit_resolves_relative_and_repo_root_markdown_references(tmp_path) -> None:
    _write(tmp_path / "README.md", "Root [doc](docs/development/codex_task_template.md).\n")
    _write(tmp_path / "docs/development/codex_task_template.md", "See [local](local.md).\n")
    _write(tmp_path / "docs/development/local.md", "# Local\n")

    report = audit_repository(tmp_path)

    assert _findings_by_category(report, "missing_markdown_reference") == []


def test_audit_reports_artifact_directory_candidates_without_git(tmp_path) -> None:
    _write(tmp_path / "AGENTS.md", "# Entry\n")
    _write(tmp_path / "artifacts/internal_event_coverage_audit.json", "{}\n")

    report = audit_repository(tmp_path)

    artifacts = _findings_by_category(report, "tracked_artifact_candidate")
    assert len(artifacts) == 1
    assert artifacts[0].path == "artifacts/internal_event_coverage_audit.json"


def test_audit_reports_aicrm_next_debug_and_legacy_markers(tmp_path) -> None:
    _write(tmp_path / "AGENTS.md", "# Entry\n")
    _write(
        tmp_path / "aicrm_next/example/service.py",
        "print('debug')\n# TODO: retire production_compat marker\n",
    )

    report = audit_repository(tmp_path)

    categories = {finding.category for finding in report.findings}
    assert "aicrm_next_print_marker" in categories
    assert "aicrm_next_todo_marker" in categories
    assert "aicrm_next_legacy_marker" in categories


def test_write_report_files_outputs_markdown_and_json(tmp_path) -> None:
    _write(tmp_path / "AGENTS.md", "# Entry\n")
    report = audit_repository(tmp_path)

    markdown_output = tmp_path / "docs/cleanup/repo_hygiene_report.md"
    json_output = tmp_path / "docs/cleanup/repo_hygiene_report.json"
    write_report_files(report, markdown_output=markdown_output, json_output=json_output)

    assert "# Repo Hygiene Audit" in markdown_output.read_text(encoding="utf-8")
    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert payload["root"] == "."
    assert "Findings" in render_human_summary(report)
