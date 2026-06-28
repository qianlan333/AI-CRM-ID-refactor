from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MARKDOWN_PATTERNS = (
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "docs/development/*.md",
    "skills/**/*.md",
)
ARTIFACT_DIRS = ("artifacts", "outputs", "exports", "dist")
AICRM_MARKERS = (
    ("console", "console."),
    ("debug", "debug"),
    ("debug", "DEBUG"),
    ("debug", "debugger"),
    ("print", "print("),
    ("todo", "TODO"),
    ("fixme", "FIXME"),
    ("legacy", "legacy_flask"),
    ("legacy", "openclaw_service"),
    ("legacy", "production_compat"),
    ("legacy", "forward_to_legacy_flask"),
)
TEXT_EXTENSIONS = {".css", ".html", ".js", ".json", ".md", ".py", ".ts", ".txt", ".yaml", ".yml"}
LINK_RE = re.compile(r"!?\[[^\]]*]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FULL_LINK_RE = re.compile(r"!?\[[^\]]*]\([^)]+\)")
PATH_RE = re.compile(
    r"(?<![\w:.])(?:\.{0,2}/)?(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\."
    r"(?:css|html|json|js|md|py|sh|toml|txt|ya?ml)(?![A-Za-z0-9_.-])"
)


@dataclass(frozen=True)
class RepoFinding:
    category: str
    path: str
    line: int | None
    detail: str
    severity: str = "info"
    next_action: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "path": self.path,
            "line": self.line,
            "detail": self.detail,
            "severity": self.severity,
            "next_action": self.next_action,
        }


@dataclass(frozen=True)
class HygieneReport:
    root: str
    scanned_markdown_files: list[str]
    findings: list[RepoFinding]

    def as_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            "scanned_markdown_files": self.scanned_markdown_files,
            "finding_count": len(self.findings),
            "findings": [finding.as_dict() for finding in self.findings],
        }


def audit_repository(root: Path = ROOT) -> HygieneReport:
    root = root.resolve()
    markdown_files = _iter_markdown_files(root)
    findings: list[RepoFinding] = []
    findings.extend(_audit_markdown_references(root, markdown_files))
    findings.extend(_audit_tracked_artifacts(root))
    findings.extend(_audit_agent_entry_docs(root, markdown_files))
    findings.extend(_audit_aicrm_markers(root))
    return HygieneReport(
        root=".",
        scanned_markdown_files=[_display_path(path, root) for path in markdown_files],
        findings=sorted(findings, key=lambda finding: (finding.category, finding.path, finding.line or 0, finding.detail)),
    )


def render_human_summary(report: HygieneReport) -> str:
    counts: dict[str, int] = {}
    for finding in report.findings:
        counts[finding.category] = counts.get(finding.category, 0) + 1
    lines = [
        "# Repo Hygiene Audit",
        "",
        f"- Root: `{report.root}`",
        f"- Markdown files scanned: {len(report.scanned_markdown_files)}",
        f"- Findings: {len(report.findings)}",
        "",
        "## Finding Summary",
        "",
    ]
    if counts:
        for category, count in sorted(counts.items()):
            lines.append(f"- `{category}`: {count}")
    else:
        lines.append("- No findings.")
    lines.extend(["", "## Findings", ""])
    if report.findings:
        for finding in report.findings:
            location = finding.path if finding.line is None else f"{finding.path}:{finding.line}"
            lines.append(f"- **{finding.category}** `{location}` - {finding.detail}")
            if finding.next_action:
                lines.append(f"  - Next: {finding.next_action}")
    else:
        lines.append("No findings.")
    lines.extend(
        [
            "",
            "## Suggested Cleanup Batches",
            "",
            "- Fix stale agent-entry references before changing runtime code.",
            "- Decide whether tracked artifact directories are evidence or generated output.",
            "- Review debug/TODO/legacy markers in `aicrm_next/` before expanding lint gates.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_report_files(
    report: HygieneReport,
    *,
    markdown_output: Path,
    json_output: Path,
) -> None:
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(render_human_summary(report), encoding="utf-8")
    json_output.write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit repository hygiene without changing runtime behavior.")
    parser.add_argument("--root", default=str(ROOT), help="Repository root to scan.")
    parser.add_argument("--markdown-output", default="docs/cleanup/repo_hygiene_report.md")
    parser.add_argument("--json-output", default="docs/cleanup/repo_hygiene_report.json")
    parser.add_argument("--no-write", action="store_true", help="Print the human summary without writing report files.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    report = audit_repository(root)
    if not args.no_write:
        write_report_files(
            report,
            markdown_output=root / args.markdown_output,
            json_output=root / args.json_output,
        )
    print(render_human_summary(report))
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    return 0


def _iter_markdown_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in DEFAULT_MARKDOWN_PATTERNS:
        files.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(files)


def _audit_markdown_references(root: Path, markdown_files: list[Path]) -> list[RepoFinding]:
    findings: list[RepoFinding] = []
    seen: set[tuple[str, int, str]] = set()
    for path in markdown_files:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for candidate in _extract_internal_path_candidates(line):
                normalized = _normalize_reference(candidate)
                if not normalized or _reference_exists(root, path, normalized):
                    continue
                key = (_display_path(path, root), line_number, normalized)
                if key in seen:
                    continue
                seen.add(key)
                findings.append(
                    RepoFinding(
                        category="missing_markdown_reference",
                        path=key[0],
                        line=line_number,
                        detail=f"`{normalized}` does not resolve from the source file or repository root.",
                        severity="warn",
                        next_action="Remove the stale reference or restore a canonical pointer file.",
                    )
                )
    return findings


def _audit_tracked_artifacts(root: Path) -> list[RepoFinding]:
    tracked = _git_ls_files(root, ARTIFACT_DIRS)
    if not tracked:
        tracked = [
            _display_path(path, root)
            for directory in ARTIFACT_DIRS
            for path in sorted((root / directory).rglob("*"))
            if path.is_file()
        ]
    return [
        RepoFinding(
            category="tracked_artifact_candidate",
            path=path,
            line=None,
            detail="File lives under a generated-output style directory.",
            severity="review",
            next_action="Classify as durable evidence under docs/reports/evidence/ or generated output ignored by git.",
        )
        for path in tracked
    ]


def _audit_agent_entry_docs(root: Path, markdown_files: list[Path]) -> list[RepoFinding]:
    entry_files = [
        path
        for path in markdown_files
        if path.name in {"AGENTS.md", "CLAUDE.md", "README.md", "SKILL.md"} or "skills" in path.parts
    ]
    findings: list[RepoFinding] = []
    if len(entry_files) > 1:
        entry_display = ", ".join(_display_path(path, root) for path in entry_files)
        findings.append(
            RepoFinding(
                category="agent_entry_overlap",
                path="agent-entry-docs",
                line=None,
                detail=f"Multiple agent-facing entry documents exist and should share the same canonical preflight wording: {entry_display}.",
                severity="review",
                next_action="Keep AGENTS.md and docs/development/ai_crm_next_architecture_skill.md as the canonical starting point.",
            )
        )
    for finding in _audit_markdown_references(root, entry_files):
        findings.append(
            RepoFinding(
                category="agent_entry_missing_reference",
                path=finding.path,
                line=finding.line,
                detail=finding.detail,
                severity=finding.severity,
                next_action="Align agent entry docs before broader cleanup PRs.",
            )
        )
    claude = root / "CLAUDE.md"
    if claude.exists():
        content = claude.read_text(encoding="utf-8")
        if "crm-prod" in content or "www.youcangogogo.com" in content:
            findings.append(
                RepoFinding(
                    category="agent_entry_ops_detail",
                    path="CLAUDE.md",
                    line=None,
                    detail="Agent entry doc includes production connection details.",
                    severity="review",
                    next_action="Consider replacing with a safe stub and moving operational details to private ops docs.",
                )
            )
    return findings


def _audit_aicrm_markers(root: Path) -> list[RepoFinding]:
    base = root / "aicrm_next"
    if not base.exists():
        return []
    findings: list[RepoFinding] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_EXTENSIONS or "__pycache__" in path.parts:
            continue
        rel = _display_path(path, root)
        for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            for marker_type, marker in AICRM_MARKERS:
                if marker in line:
                    findings.append(
                        RepoFinding(
                            category=f"aicrm_next_{marker_type}_marker",
                            path=rel,
                            line=line_number,
                            detail=f"`{marker}` appears in `aicrm_next/`.",
                            severity="review",
                            next_action="Review marker before turning hygiene checks into enforcement.",
                        )
                    )
    return findings


def _extract_internal_path_candidates(line: str) -> list[str]:
    candidates = [match.group(1) for match in LINK_RE.finditer(line)]
    masked_line = FULL_LINK_RE.sub("", line)
    if not _contains_external_absolute_path(masked_line):
        candidates.extend(match.group(0) for match in PATH_RE.finditer(masked_line))
    return candidates


def _normalize_reference(candidate: str) -> str | None:
    value = candidate.strip().strip("`'\"").rstrip(".,;:")
    if not value or value.startswith("#"):
        return None
    if "://" in value or value.startswith(("mailto:", "app://")):
        return None
    if value.startswith((".claude/", "github.com/")):
        return None
    value = value.split("#", 1)[0].split("?", 1)[0]
    if _is_external_absolute_reference(value):
        return None
    if not value:
        return None
    return value


def _contains_external_absolute_path(line: str) -> bool:
    return any(prefix in line for prefix in ("/home/", "/tmp/", "/usr/", "/var/", "/etc/"))


def _is_external_absolute_reference(value: str) -> bool:
    if not value.startswith("/"):
        return False
    return value.startswith(("/home/", "/tmp/", "/usr/", "/var/", "/etc/", "/github.com/"))


def _reference_exists(root: Path, source: Path, reference: str) -> bool:
    ref_path = Path(reference)
    candidates = []
    if ref_path.is_absolute():
        candidates.append(root / reference.lstrip("/"))
    else:
        candidates.extend([source.parent / ref_path, root / ref_path])
    return any(candidate.exists() for candidate in candidates)


def _git_ls_files(root: Path, directories: Iterable[str]) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--", *directories],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
