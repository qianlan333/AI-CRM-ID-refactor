#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PHASE4A_MD = ROOT / "docs/development/phase_4a_internal_write_candidate_selection.md"
PHASE4A_YAML = ROOT / "docs/development/phase_4a_internal_write_candidate_selection.yaml"
BACKLOG_YAML = ROOT / "docs/development/legacy_replacement_backlog.yaml"
REQUIRED_DOCS = [
    PHASE4A_MD,
    PHASE4A_YAML,
    ROOT / "docs/development/phase_3_closure_and_phase_4_readiness.md",
    ROOT / "docs/development/phase_3_closure_and_phase_4_readiness.yaml",
    BACKLOG_YAML,
]
REQUIRED_AUTH_FALSE = {
    "implementation_authorized",
    "production_cutover_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "db_schema_change_authorized",
    "real_external_call_authorized",
}
REQUIRED_FORBIDDEN_FIRST_BATCH = {
    "payment",
    "oauth",
    "wecom_external_call",
    "timer",
    "automation_execution",
    "media_upload",
    "public_submit_external_push",
    "openclaw_mcp_real_external_call",
}
REQUIRED_CANDIDATE_RULES = {
    "bounded_internal_write_only",
    "no_real_external_side_effect",
    "fallback_retained",
    "rollback_required",
    "idempotency_required",
    "audit_or_operator_identity_required",
    "checker_required",
    "production_smoke_required",
    "fixture_success_forbidden",
}
REQUIRED_CANDIDATE_FIELDS = {
    "route_family",
    "capability_owner",
    "replacement_phase",
    "replacement_category",
    "decision",
    "risks",
    "excluded_side_effects",
    "required_idempotency",
    "required_audit_operator_identity",
    "required_validation",
    "required_rollback",
    "fallback_required_until",
    "required_checker",
    "required_smoke",
    "business_continuity_requirement",
}
FORBIDDEN_RECOMMENDED_TERMS = {
    "payment": ("payment",),
    "pay": ("payment",),
    "oauth": ("oauth",),
    "wecom external": ("wecom_external_call",),
    "callback": ("callback",),
    "run-due": ("run_due", "run-due"),
    "timer": ("timer",),
    "execution": ("workflow_execution", "automation_execution", "execution"),
    "send": ("outbound_send", "send"),
    "upload": ("media_upload", "upload"),
    "openclaw": ("openclaw_mcp_real_external_call",),
    "mcp": ("openclaw_mcp_real_external_call",),
    "public submit": ("public_submit_external_push", "public_submit"),
    "external push": ("public_submit_external_push", "external_push"),
}
PROTECTED_PREFIXES = (
    "aicrm_next/",
    "wecom_ability_service/",
    "migrations/",
    "deploy",
    "systemd",
    "nginx",
)
PROTECTED_EXACT = {
    "app.py",
    "legacy_flask_app.py",
}
PROTECTED_SUBSTRINGS = {
    "production_compat",
}
ALLOWED_CHANGED_FILES = {
    "aicrm_next/automation_engine/api.py",
    "aicrm_next/automation_engine/application.py",
    "aicrm_next/automation_engine/domain.py",
    "aicrm_next/automation_engine/dto.py",
    "aicrm_next/automation_engine/repo.py",
    "aicrm_next/automation_engine/profile_segments.py",
    "docs/development/phase_4a_internal_write_candidate_selection.md",
    "docs/development/phase_4a_internal_write_candidate_selection.yaml",
    "docs/development/phase_4b_profile_segment_template_implementation_plan.md",
    "docs/development/phase_4b_profile_segment_template_implementation_plan.yaml",
    "docs/development/phase_4c_profile_segment_template_native_contract.md",
    "tools/check_phase4a_internal_write_candidate_selection.py",
    "tools/check_phase4b_profile_segment_template_plan.py",
    "tools/check_phase4c_profile_segment_template_native_contract.py",
    "tests/test_phase4a_internal_write_candidate_selection.py",
    "tests/test_phase4b_profile_segment_template_plan.py",
    "tests/test_phase4c_profile_segment_template_native_contract.py",
}


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in inner.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def _strip_yaml_comments(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index].rstrip()
    return line.rstrip()


def _yaml_lines(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        stripped = _strip_yaml_comments(raw)
        if not stripped.strip():
            continue
        lines.append((len(stripped) - len(stripped.lstrip(" ")), stripped.strip()))
    return lines


def _parse_yaml_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    current_indent, current_text = lines[index]
    if current_indent < indent:
        return {}, index
    if current_text.startswith("- "):
        result: list[Any] = []
        while index < len(lines):
            line_indent, text = lines[index]
            if line_indent != indent or not text.startswith("- "):
                break
            item_text = text[2:].strip()
            index += 1
            if not item_text:
                value, index = _parse_yaml_block(lines, index, indent + 2)
                result.append(value)
                continue
            if ":" not in item_text:
                result.append(_parse_scalar(item_text))
                continue
            key, raw_value = item_text.split(":", 1)
            item: dict[str, Any] = {}
            raw_value = raw_value.strip()
            if raw_value:
                item[key.strip()] = _parse_scalar(raw_value)
            else:
                value, index = _parse_yaml_block(lines, index, indent + 2)
                item[key.strip()] = value
            while index < len(lines):
                child_indent, child_text = lines[index]
                if child_indent <= indent:
                    break
                if child_indent == indent + 2 and not child_text.startswith("- ") and ":" in child_text:
                    child_key, child_raw_value = child_text.split(":", 1)
                    child_raw_value = child_raw_value.strip()
                    index += 1
                    if child_raw_value:
                        item[child_key.strip()] = _parse_scalar(child_raw_value)
                    else:
                        value, index = _parse_yaml_block(lines, index, child_indent + 2)
                        item[child_key.strip()] = value
                else:
                    break
            result.append(item)
        return result, index

    result: dict[str, Any] = {}
    while index < len(lines):
        line_indent, text = lines[index]
        if line_indent != indent or text.startswith("- "):
            break
        key, raw_value = text.split(":", 1)
        raw_value = raw_value.strip()
        index += 1
        if raw_value:
            result[key.strip()] = _parse_scalar(raw_value)
        else:
            value, index = _parse_yaml_block(lines, index, indent + 2)
            result[key.strip()] = value
    return result, index


def _load_yaml_without_dependency(text: str) -> dict[str, Any]:
    data, _ = _parse_yaml_block(_yaml_lines(text), 0, 0)
    return data if isinstance(data, dict) else {}


def load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ModuleNotFoundError:
        return _load_yaml_without_dependency(text)


def check_required_docs() -> dict[str, Any]:
    blockers = [f"{_rel(path)} missing" for path in REQUIRED_DOCS if not path.exists()]
    return {"ok": not blockers, "blockers": blockers}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _candidate_by_id(candidates: list[dict[str, Any]], candidate_id: str) -> dict[str, Any] | None:
    for candidate in candidates:
        if str(candidate.get("id") or "") == candidate_id:
            return candidate
    return None


def _text_values(candidate: dict[str, Any], keys: tuple[str, ...]) -> str:
    return " ".join(str(candidate.get(key) or "") for key in keys).lower()


def _excluded_terms(candidate: dict[str, Any]) -> set[str]:
    excluded = candidate.get("excluded_side_effects")
    if isinstance(excluded, list):
        return {str(item).lower().replace("-", "_").replace(" ", "_") for item in excluded}
    return {str(excluded or "").lower().replace("-", "_").replace(" ", "_")}


def _term_excluded(candidate: dict[str, Any], aliases: tuple[str, ...]) -> bool:
    excluded = _excluded_terms(candidate)
    return any(alias.lower().replace("-", "_").replace(" ", "_") in excluded for alias in aliases)


def check_phase4a_yaml() -> dict[str, Any]:
    blockers: list[str] = []
    if not PHASE4A_YAML.exists():
        return {"ok": False, "blockers": [f"{_rel(PHASE4A_YAML)} missing"], "candidates": []}
    data = load_yaml(PHASE4A_YAML)

    if data.get("version") != 1:
        blockers.append("phase4a yaml version must be 1")
    if data.get("status") != "phase_4a_planning_only_no_runtime_change":
        blockers.append("phase4a yaml status must be phase_4a_planning_only_no_runtime_change")

    phase4a = data.get("phase_4a") or {}
    for field in sorted(REQUIRED_AUTH_FALSE):
        if phase4a.get(field) is not False:
            blockers.append(f"phase_4a.{field} must be false")

    forbidden = set(str(item) for item in _as_list(data.get("forbidden_first_batch")))
    missing_forbidden = sorted(REQUIRED_FORBIDDEN_FIRST_BATCH - forbidden)
    if missing_forbidden:
        blockers.append(f"forbidden_first_batch missing {missing_forbidden}")

    rules = data.get("candidate_rules") or {}
    for field in sorted(REQUIRED_CANDIDATE_RULES):
        if rules.get(field) is not True:
            blockers.append(f"candidate_rules.{field} must be true")

    candidates = [item for item in _as_list(data.get("candidates")) if isinstance(item, dict)]
    if not (2 <= len(candidates) <= 4):
        blockers.append(f"candidates count must be between 2 and 4, found {len(candidates)}")
    for candidate in candidates:
        label = str(candidate.get("id") or candidate.get("route_family") or "<missing>")
        missing = sorted(field for field in REQUIRED_CANDIDATE_FIELDS if not candidate.get(field))
        if missing:
            blockers.append(f"{label} missing required fields {missing}")
        if candidate.get("replacement_phase") != "phase_4_internal_write":
            blockers.append(f"{label} replacement_phase must be phase_4_internal_write")
        if candidate.get("replacement_category") not in {"internal_write", "shell_or_navigation"}:
            blockers.append(f"{label} replacement_category must be internal_write or shell_or_navigation")
        if candidate.get("decision") not in {"recommended", "evaluate_later", "deferred"}:
            blockers.append(f"{label} decision must be recommended/evaluate_later/deferred")
        continuity = str(candidate.get("business_continuity_requirement") or "").lower()
        if "fallback" not in continuity or "daily" not in continuity:
            blockers.append(f"{label} business_continuity_requirement must mention daily continuity and fallback")

    recommended_candidates = [candidate for candidate in candidates if candidate.get("decision") == "recommended"]
    for candidate in recommended_candidates:
        label = str(candidate.get("id") or candidate.get("route_family") or "<missing>")
        text = _text_values(candidate, ("route_family", "capability_owner", "notes"))
        for term, aliases in FORBIDDEN_RECOMMENDED_TERMS.items():
            if term in text and not _term_excluded(candidate, aliases):
                blockers.append(f"{label} recommended scope contains forbidden term {term!r} without excluded_side_effects")

    recommended = data.get("recommended_phase_4b") or {}
    candidate_id = str(recommended.get("candidate_id") or "")
    notes = str(recommended.get("notes") or "")
    if recommended.get("approval_required") is not True:
        blockers.append("recommended_phase_4b.approval_required must be true")
    if recommended.get("implementation_pr_required") is not True:
        blockers.append("recommended_phase_4b.implementation_pr_required must be true")
    if candidate_id:
        matched = _candidate_by_id(candidates, candidate_id)
        if not matched:
            blockers.append("recommended_phase_4b.candidate_id must match a candidate")
        elif matched.get("decision") != "recommended":
            blockers.append("recommended_phase_4b.candidate_id must point to a recommended candidate")
    elif "no implementation candidate approved yet" not in notes.lower():
        blockers.append("recommended_phase_4b.candidate_id may be empty only when notes say no implementation candidate approved yet")

    return {
        "ok": not blockers,
        "blockers": blockers,
        "candidate_count": len(candidates),
        "recommended_candidate_id": candidate_id,
    }


def _route_prefix(value: str) -> str:
    value = value.strip().strip('"').strip("'")
    value = value.replace("{path:path}", "").replace("*", "")
    return value.rstrip("/")


def _is_traceable(candidate_family: str, backlog_pattern: str) -> bool:
    family = candidate_family.lower()
    pattern = backlog_pattern.lower()
    prefix = _route_prefix(pattern).lower()
    if pattern in family or prefix in family:
        return True
    if "narrowed" in family and prefix and prefix in family:
        return True
    return False


def check_backlog_traceability() -> dict[str, Any]:
    blockers: list[str] = []
    if not PHASE4A_YAML.exists() or not BACKLOG_YAML.exists():
        return {"ok": False, "blockers": ["phase4a yaml or backlog yaml missing"]}
    phase4a = load_yaml(PHASE4A_YAML)
    backlog = load_yaml(BACKLOG_YAML)
    candidates = [item for item in _as_list(phase4a.get("candidates")) if isinstance(item, dict)]
    entries = [item for item in _as_list(backlog.get("entries")) if isinstance(item, dict)]
    patterns = [str(entry.get("route_pattern") or "") for entry in entries]

    traces: dict[str, list[str]] = {}
    for candidate in candidates:
        label = str(candidate.get("id") or candidate.get("route_family") or "<missing>")
        family = str(candidate.get("route_family") or "")
        matches = [pattern for pattern in patterns if _is_traceable(family, pattern)]
        if not matches:
            blockers.append(f"{label} route_family is not traceable to legacy_replacement_backlog.yaml")
        traces[label] = matches
    return {"ok": not blockers, "blockers": blockers, "traces": traces}


def _run_git(args: list[str]) -> tuple[bool, list[str], str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception as exc:
        return False, [], str(exc)
    if completed.returncode != 0:
        return False, [], completed.stderr.strip()
    return True, [line.strip() for line in completed.stdout.splitlines() if line.strip()], ""


def _changed_files_from_git() -> tuple[set[str], list[str]]:
    warnings: list[str] = []
    changed: set[str] = set()
    for args in (["diff", "--name-only", "origin/main...HEAD"], ["diff", "--name-only", "origin/main"]):
        ok, files, error = _run_git(args)
        if ok:
            changed.update(files)
        else:
            warnings.append(f"git {' '.join(args)} unavailable: {error}")
    ok, files, error = _run_git(["ls-files", "--others", "--exclude-standard"])
    if ok:
        changed.update(files)
    else:
        warnings.append(f"git ls-files --others unavailable: {error}")
    return changed, warnings


def _is_protected_runtime_file(path: str) -> bool:
    if path in PROTECTED_EXACT:
        return True
    if any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES):
        return True
    if any(token in path for token in PROTECTED_SUBSTRINGS):
        return True
    return False


def check_no_runtime_changes() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    blockers: list[str] = []
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    runtime_changes = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected_runtime_file(path))
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4A planning scope: {unexpected}")
    if runtime_changes:
        blockers.append(f"runtime/protected files changed: {runtime_changes}")
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "changed_files": sorted(changed),
    }


def build_report() -> dict[str, Any]:
    checks = {
        "required_docs": check_required_docs(),
        "phase4a_yaml": check_phase4a_yaml(),
        "backlog_traceability": check_backlog_traceability(),
        "no_runtime_changes": check_no_runtime_changes(),
    }
    blockers: list[str] = []
    warnings: list[str] = []
    for name, check in checks.items():
        for blocker in check.get("blockers", []):
            blockers.append(f"{name}: {blocker}")
        for warning in check.get("warnings", []):
            warnings.append(f"{name}: {warning}")
    return {
        "overall": "PASS" if not blockers else "FAIL",
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "candidate_count": checks["phase4a_yaml"].get("candidate_count", 0),
        "recommended_candidate_id": checks["phase4a_yaml"].get("recommended_candidate_id", ""),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 4A Internal Write Candidate Selection Check",
        "",
        f"- overall: {report['overall']}",
        f"- candidate_count: {report.get('candidate_count', 0)}",
        f"- recommended_candidate_id: {report.get('recommended_candidate_id', '')}",
        "",
        "## Blockers",
    ]
    blockers = report.get("blockers") or []
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Warnings")
    warnings = report.get("warnings") or []
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)

    report = build_report()
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(f"overall: {report['overall']}")
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
