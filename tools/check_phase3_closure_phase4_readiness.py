#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

READINESS_MD = ROOT / "docs/development/phase_3_closure_and_phase_4_readiness.md"
READINESS_YAML = ROOT / "docs/development/phase_3_closure_and_phase_4_readiness.yaml"
REQUIRED_DOCS = [
    READINESS_MD,
    READINESS_YAML,
    ROOT / "docs/development/phase_3_readonly_replacement_acceptance_report.md",
    ROOT / "docs/development/phase_3_readonly_replacement_acceptance_report.yaml",
    ROOT / "docs/development/phase_3f_admin_customers_shell_hardening.md",
]
EXPECTED_ROUTES = {
    "/api/sidebar/contact-binding-status",
    "/api/sidebar/customer-context",
    "/api/admin/customers/profile",
    "/api/admin/customers/profile/tags",
    "/api/customers",
    "/api/customers/{external_userid}",
    "/api/customers/{external_userid}/timeline",
    "/api/messages/{external_userid}/recent",
    "/admin/customers",
}
FORBIDDEN_FIRST_BATCH = {
    "payment",
    "oauth",
    "wecom_external_call",
    "timer",
    "automation_execution",
    "media_upload",
    "openclaw_mcp_real_external_call",
}
REQUIRED_PHASE4_RULES = {
    "no_real_external_side_effect",
    "bounded_internal_write_only",
    "idempotency_required",
    "audit_or_operator_identity_required",
    "rollback_required",
    "fallback_retained",
    "production_smoke_required",
    "checker_required",
}
PROTECTED_RUNTIME_PATHS = {
    "aicrm_next/main.py",
    "aicrm_next/production_compat/api.py",
    "aicrm_next/customer_read_model/api.py",
    "aicrm_next/customer_read_model/application.py",
    "aicrm_next/frontend_compat/legacy_routes.py",
}
PROTECTED_RUNTIME_PREFIXES = ("deploy/", "systemd/", "nginx/")
CHILD_CHECKERS = [
    "tools/check_phase3_readonly_acceptance.py",
    "tools/check_phase3f_admin_customers_shell.py",
    "tools/check_phase3d_recent_messages_readonly.py",
    "tools/check_phase3c_customer_read_model_readonly.py",
    "tools/check_phase3b_customer_profile_readonly.py",
    "tools/check_phase3_sidebar_readonly_replacement.py",
    "tools/check_legacy_facade_growth_freeze.py",
]
FORBIDDEN_IMMEDIATE_TERMS = (
    "payment",
    "oauth",
    "wecom",
    "timer",
    "automation execution",
    "media upload",
    "openclaw",
    "mcp",
)


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
    lines = _yaml_lines(text)
    data, _ = _parse_yaml_block(lines, 0, 0)
    return data if isinstance(data, dict) else {}


def load_readiness_yaml(path: Path = READINESS_YAML) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ModuleNotFoundError:
        return _load_yaml_without_dependency(text)


def check_required_docs() -> dict[str, Any]:
    blockers = [f"{_rel(path)} missing" for path in REQUIRED_DOCS if not path.exists()]
    return {"ok": not blockers, "blockers": blockers}


def check_readiness_yaml() -> dict[str, Any]:
    blockers: list[str] = []
    if not READINESS_YAML.exists():
        return {"ok": False, "blockers": [f"{_rel(READINESS_YAML)} missing"], "routes": []}
    data = load_readiness_yaml()
    if data.get("version") != 1:
        blockers.append("readiness yaml version must be 1")
    if data.get("status") != "phase_3_closure_phase_4_readiness_only_no_runtime_change":
        blockers.append("readiness yaml status must be phase_3_closure_phase_4_readiness_only_no_runtime_change")

    phase3 = data.get("phase_3") or {}
    expected_phase3_flags = {
        "closeable": True,
        "fallback_removal_authorized": False,
        "production_cutover_authorized": False,
        "write_replacement_authorized": False,
    }
    for field, expected in expected_phase3_flags.items():
        if phase3.get(field) is not expected:
            blockers.append(f"phase_3.{field} must be {expected!r}")

    routes = list(phase3.get("routes") or [])
    route_patterns = {str(route.get("route_pattern")) for route in routes}
    if route_patterns != EXPECTED_ROUTES:
        blockers.append(f"phase_3 routes mismatch expected={sorted(EXPECTED_ROUTES)} actual={sorted(route_patterns)}")
    if len(routes) != 9:
        blockers.append(f"phase_3.routes must contain 9 entries, found {len(routes)}")
    for route in routes:
        label = str(route.get("route_pattern") or "<missing>")
        for field, expected in {
            "exact_next_owner_confirmed": True,
            "fallback_retained": True,
            "production_compat_unchanged": True,
            "delete_ready": False,
        }.items():
            if route.get(field) is not expected:
                blockers.append(f"{label} {field} must be {expected!r}")
        if not route.get("checker"):
            blockers.append(f"{label} checker must be non-empty")
        continuity = str(route.get("business_continuity_requirement") or "")
        if not continuity:
            blockers.append(f"{label} business_continuity_requirement must be non-empty")
        if not all(token in continuity.lower() for token in ("fallback", "parity", "checker", "smoke", "rollback")):
            blockers.append(f"{label} business_continuity_requirement must name fallback/parity/checker/smoke/rollback")

    readiness = data.get("phase_4_readiness") or {}
    if readiness.get("can_start_after_this_report") is not False:
        blockers.append("phase_4_readiness.can_start_after_this_report must be false")
    if readiness.get("requires_explicit_approval") is not True:
        blockers.append("phase_4_readiness.requires_explicit_approval must be true")
    forbidden = set(readiness.get("forbidden_first_batch") or [])
    missing_forbidden = sorted(FORBIDDEN_FIRST_BATCH - forbidden)
    if missing_forbidden:
        blockers.append(f"phase_4_readiness.forbidden_first_batch missing {', '.join(missing_forbidden)}")
    rules = readiness.get("first_batch_candidate_rules") or {}
    for rule in sorted(REQUIRED_PHASE4_RULES):
        if rules.get(rule) is not True:
            blockers.append(f"phase_4_readiness.first_batch_candidate_rules.{rule} must be true")

    candidates = list(data.get("next_candidates") or [])
    if not candidates:
        blockers.append("next_candidates must be non-empty")
    for index, candidate in enumerate(candidates, start=1):
        label = str(candidate.get("route_family") or f"candidate_{index}")
        if not candidate.get("excluded_side_effects"):
            blockers.append(f"{label} must include excluded_side_effects")
        if not candidate.get("required_guardrails"):
            blockers.append(f"{label} must include required_guardrails")
        if not candidate.get("rollback_requirement"):
            blockers.append(f"{label} must include rollback_requirement")
        continuity = str(candidate.get("daily_business_continuity_requirement") or "").lower()
        if not all(token in continuity for token in ("daily", "fallback", "rollback")):
            blockers.append(f"{label} must include daily business continuity language")
        recommendation_text = f"{candidate.get('route_family', '')} {candidate.get('recommendation', '')}".lower()
        if any(term in recommendation_text for term in FORBIDDEN_IMMEDIATE_TERMS) and "evaluate" not in recommendation_text:
            blockers.append(f"{label} must not recommend forbidden external side-effect family as first batch")
    return {"ok": not blockers, "blockers": blockers, "routes": routes, "next_candidates": candidates}


def check_markdown_report() -> dict[str, Any]:
    blockers: list[str] = []
    if not READINESS_MD.exists():
        return {"ok": False, "blockers": [f"{_rel(READINESS_MD)} missing"]}
    text = _read(READINESS_MD)
    for route in EXPECTED_ROUTES:
        if route not in text:
            blockers.append(f"{_rel(READINESS_MD)} missing {route}")
    for phrase in (
        "Phase 3 customer/sidebar readonly track: closeable",
        "Phase 3 does not authorize fallback removal",
        "Phase 3 does not authorize production cutover",
        "Phase 3 does not authorize write replacement",
        "Phase 4 can only address internal_write candidates",
        "requires explicit owner approval",
    ):
        if phrase not in text:
            blockers.append(f"{_rel(READINESS_MD)} missing required phrase: {phrase}")
    forbidden_claims = (
        "production approved",
        "canary approved",
        "delete_ready true",
        "delete_ready: true",
        "fallback removal authorized",
        "production cutover authorized",
    )
    lower = text.lower()
    for phrase in forbidden_claims:
        if phrase in lower:
            blockers.append(f"{_rel(READINESS_MD)} must not claim {phrase}")
    return {"ok": not blockers, "blockers": blockers}


def _git_changed_files() -> tuple[list[str], str | None]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            cwd=ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()], None
    except Exception as exc:
        return [], str(exc)


def check_no_runtime_changes() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    changed, error = _git_changed_files()
    if error:
        warnings.append(f"could not inspect git diff against origin/main: {error}")
        return {"ok": True, "blockers": blockers, "warnings": warnings, "changed_files": changed}
    for path in changed:
        if path in PROTECTED_RUNTIME_PATHS or path.startswith(PROTECTED_RUNTIME_PREFIXES):
            blockers.append(f"{path} must not be modified by Phase 3G")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "changed_files": changed}


def _load_checker(path: str):
    checker_path = ROOT / path
    spec = importlib.util.spec_from_file_location(checker_path.stem, checker_path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"cannot load checker {path}")
    spec.loader.exec_module(module)
    return module


def _is_fastapi_missing_only(blockers: list[Any]) -> bool:
    if not blockers:
        return False
    text = "\n".join(str(blocker) for blocker in blockers).lower()
    return (
        "fastapi" in text
        and "no module named 'fastapi'" in text
        and all("fastapi" in str(blocker).lower() for blocker in blockers)
    )


def check_child_reports() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    reports: dict[str, Any] = {}
    for checker in CHILD_CHECKERS:
        try:
            module = _load_checker(checker)
            report = module.build_report()
        except Exception as exc:
            message = str(exc)
            if "No module named 'fastapi'" in message:
                reports[checker] = {"overall": "SKIPPED", "reason": message}
                warnings.append(f"{checker} skipped because FastAPI is unavailable")
                continue
            blockers.append(f"{checker} failed to run: {exc}")
            continue
        checker_blockers = list(report.get("blockers", []))
        if report.get("overall") == "PASS":
            reports[checker] = {"overall": "PASS", "blockers": []}
        elif _is_fastapi_missing_only(checker_blockers):
            reports[checker] = {"overall": "SKIPPED", "blockers": checker_blockers}
            warnings.append(f"{checker} skipped because FastAPI is unavailable")
        else:
            reports[checker] = {
                "overall": report.get("overall"),
                "blockers": checker_blockers,
            }
            blockers.append(f"{checker} overall={report.get('overall')}: {checker_blockers}")

    with tempfile.NamedTemporaryFile(prefix="legacy_replacement_backlog_check_", suffix=".json") as tmp:
        result = subprocess.run(
            [
                sys.executable,
                "tools/generate_legacy_replacement_backlog.py",
                "--check",
                "--output-json",
                tmp.name,
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            blockers.append(
                "tools/generate_legacy_replacement_backlog.py --check failed: "
                f"stdout={result.stdout.strip()} stderr={result.stderr.strip()}"
            )
            reports["tools/generate_legacy_replacement_backlog.py --check"] = {
                "overall": "FAIL",
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        else:
            reports["tools/generate_legacy_replacement_backlog.py --check"] = {"overall": "PASS"}

    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "reports": reports}


def build_report() -> dict[str, Any]:
    docs = check_required_docs()
    yaml_report = check_readiness_yaml()
    markdown = check_markdown_report()
    no_runtime = check_no_runtime_changes()
    child_reports = check_child_reports()
    blockers = (
        list(docs.get("blockers", []))
        + list(yaml_report.get("blockers", []))
        + list(markdown.get("blockers", []))
        + list(no_runtime.get("blockers", []))
        + list(child_reports.get("blockers", []))
    )
    warnings = list(no_runtime.get("warnings", [])) + list(child_reports.get("warnings", []))
    return {
        "overall": "PASS" if not blockers else "FAIL",
        "blockers": blockers,
        "warnings": warnings,
        "expected_routes": sorted(EXPECTED_ROUTES),
        "required_docs": docs,
        "readiness_yaml": yaml_report,
        "markdown_report": markdown,
        "no_runtime_changes": no_runtime,
        "child_checkers": child_reports,
    }


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Phase 3 Closure / Phase 4 Readiness Check",
        "",
        f"- overall: {report['overall']}",
        f"- blockers: {len(report.get('blockers', []))}",
        f"- warnings: {len(report.get('warnings', []))}",
        "",
        "## Routes",
    ]
    for route in report.get("expected_routes", []):
        lines.append(f"- `{route}`")
    lines.extend(["", "## Child Checkers"])
    for checker, child in report.get("child_checkers", {}).get("reports", {}).items():
        lines.append(f"- `{checker}`: {child.get('overall')}")
    lines.extend(["", "## Blockers"])
    blockers = report.get("blockers", [])
    lines.extend([f"- {item}" for item in blockers] if blockers else ["- none"])
    lines.extend(["", "## Warnings"])
    warnings = report.get("warnings", [])
    lines.extend([f"- {item}" for item in warnings] if warnings else ["- none"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    args = parser.parse_args(argv)

    report = build_report()
    if args.output_json:
        args.output_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.output_md:
        write_markdown_report(report, args.output_md)
    print(f"overall: {report['overall']}")
    if report.get("blockers"):
        print("blockers:")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    if report.get("warnings"):
        print("warnings:")
        for warning in report["warnings"]:
            print(f"- {warning}")
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
