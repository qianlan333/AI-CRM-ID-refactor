#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/autonomous_development_loop.md"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
STOP = ROOT / "docs/development/autonomous_stop_conditions.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
BACKLOG = ROOT / "docs/development/legacy_replacement_backlog.yaml"

REQUIRED_STATE_FIELDS = {
    "version",
    "status",
    "autopilot",
    "current_phase",
    "last_merged_pr",
    "last_merged_cleanup_wave",
    "recommended_next_pr",
    "owner_approval_required",
    "runtime_behavior_changed",
    "delete_ready",
    "active_safety_gates",
    "protected_runtime_boundaries",
    "next_cleanup_candidates",
}
EXPECTED_SAFETY_GATES = {
    "check_legacy_facade_growth_freeze",
    "generate_legacy_replacement_backlog",
    "check_production_route_resolution",
    "check_automerge_eligibility",
    "check_autonomous_development_loop",
    "pr_smoke",
}
EXPECTED_RUNTIME_BOUNDARIES = {
    "app.py",
    "legacy_flask_app.py",
    "aicrm_next/main.py",
    "aicrm_next/production_compat/api.py",
    "wecom_ability_service runtime",
    "migrations/deploy/nginx/systemd",
    "payment/OAuth/WeCom callback/public submit/product/checkout/order/image upload/runtime/outbound paths",
}
EXPECTED_NEXT_CANDIDATES = {
    "remaining stale non-runtime docs/reports",
    "remaining stale checker/test references",
    "governance config compaction",
}
STOP_IDS = {
    "production_owner_switch",
    "fallback_removal",
    "production_write",
    "real_external_call",
    "timer_or_execution",
    "outbound_send",
    "deploy_config",
    "destructive_migration",
    "delete_ready",
    "canary_approval",
}
PROTECTED_EXACT = {
    "app.py",
    "legacy_flask_app.py",
    "aicrm_next/main.py",
    "aicrm_next/production_compat/api.py",
}
PROTECTED_PREFIXES = (
    "wecom_ability_service/",
    "migrations/",
    "deploy/",
    "systemd/",
    "nginx/",
)
GOVERNANCE_ALLOWED_PREFIXES = (
    "docs/",
    "tools/",
    "tests/",
)
GOVERNANCE_ALLOWED_EXACT = {
    ".github/workflows/ci.yml",
    "scripts/codex_autopilot_tick.sh",
}


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value == "[]":
        return []
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
        if stripped.strip():
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
            elif ":" not in item_text:
                result.append(_parse_scalar(item_text))
            else:
                key, raw_value = item_text.split(":", 1)
                item: dict[str, Any] = {}
                if raw_value.strip():
                    item[key.strip()] = _parse_scalar(raw_value)
                else:
                    value, index = _parse_yaml_block(lines, index, indent + 2)
                    item[key.strip()] = value
                while index < len(lines) and lines[index][0] > indent:
                    nested_value, index = _parse_yaml_block(lines, index, indent + 2)
                    if isinstance(nested_value, dict):
                        item.update(nested_value)
                result.append(item)
        return result, index
    result: dict[str, Any] = {}
    while index < len(lines):
        line_indent, text = lines[index]
        if line_indent != indent or text.startswith("- "):
            break
        if ":" not in text:
            index += 1
            continue
        key, raw_value = text.split(":", 1)
        raw_value = raw_value.strip()
        index += 1
        if raw_value:
            result[key.strip()] = _parse_scalar(raw_value)
        else:
            value, index = _parse_yaml_block(lines, index, indent + 2)
            result[key.strip()] = value
    return result, index


def load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ModuleNotFoundError:
        data, _ = _parse_yaml_block(_yaml_lines(text), 0, 0)
        return data if isinstance(data, dict) else {}


def _as_strings(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value}


def _run_git(args: list[str]) -> tuple[bool, str, str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.returncode == 0, proc.stdout, proc.stderr


def _changed_files() -> set[str]:
    changed: set[str] = set()
    for args in (
        ["diff", "--name-only", "origin/main...HEAD"],
        ["diff", "--name-only"],
        ["diff", "--name-only", "--cached"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        ok, stdout, _ = _run_git(args)
        if ok:
            changed.update(line.strip() for line in stdout.splitlines() if line.strip())
    return changed


def _validate_current_state(state: dict[str, Any], blockers: list[str]) -> None:
    missing_state_fields = sorted(REQUIRED_STATE_FIELDS - set(state))
    if missing_state_fields:
        blockers.append(f"phase_execution_state missing fields: {missing_state_fields}")
    if state.get("current_phase") != "post_phase7_active_cleanup":
        blockers.append("current_phase must be post_phase7_active_cleanup")
    if state.get("last_merged_pr") != "#850":
        blockers.append("last_merged_pr must record merged cleanup PR #850")
    if state.get("last_merged_cleanup_wave") != "residual_narrative_documentation_cleanup_wave12":
        blockers.append("last_merged_cleanup_wave must record wave 12 residual narrative documentation cleanup")
    if state.get("recommended_next_pr") != "legacy_retirement_package_cleanup_wave13":
        blockers.append("recommended_next_pr must name wave 13 legacy retirement package cleanup")
    if state.get("owner_approval_required") is not False:
        blockers.append("owner_approval_required must be false for low-risk governance cleanup")
    if state.get("runtime_behavior_changed") is not False:
        blockers.append("runtime_behavior_changed must remain false")
    if state.get("delete_ready") is not False:
        blockers.append("delete_ready must remain false")

    autopilot = state.get("autopilot") if isinstance(state.get("autopilot"), dict) else {}
    if autopilot.get("enabled") is not True:
        blockers.append("autopilot.enabled must be true")
    if autopilot.get("mode") != "bounded_low_risk_governance_cleanup":
        blockers.append("autopilot.mode must be bounded_low_risk_governance_cleanup")
    if autopilot.get("runtime_changes_allowed") is not False:
        blockers.append("autopilot.runtime_changes_allowed must be false")
    if autopilot.get("admin_override_allowed") is not False:
        blockers.append("autopilot.admin_override_allowed must be false")

    gates = _as_strings(state.get("active_safety_gates"))
    if gates != EXPECTED_SAFETY_GATES:
        blockers.append(f"active_safety_gates must be exactly {sorted(EXPECTED_SAFETY_GATES)}")
    boundaries = _as_strings(state.get("protected_runtime_boundaries"))
    if boundaries != EXPECTED_RUNTIME_BOUNDARIES:
        blockers.append(f"protected_runtime_boundaries must be exactly {sorted(EXPECTED_RUNTIME_BOUNDARIES)}")
    candidates = _as_strings(state.get("next_cleanup_candidates"))
    if candidates != EXPECTED_NEXT_CANDIDATES:
        blockers.append(f"next_cleanup_candidates must be exactly {sorted(EXPECTED_NEXT_CANDIDATES)}")


def _validate_stop_conditions(stop: dict[str, Any], blockers: list[str]) -> None:
    stop_conditions = stop.get("high_risk_stop_conditions")
    if not isinstance(stop_conditions, list):
        blockers.append("autonomous_stop_conditions.high_risk_stop_conditions must be a list")
        return
    stop_ids = {str(item.get("id")) for item in stop_conditions if isinstance(item, dict)}
    missing_stop_ids = sorted(STOP_IDS - stop_ids)
    if missing_stop_ids:
        blockers.append(f"autonomous_stop_conditions missing stop ids: {missing_stop_ids}")


def _validate_changed_files(changed: set[str], blockers: list[str]) -> None:
    runtime_changed = [
        path
        for path in sorted(changed)
        if path in PROTECTED_EXACT
        or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)
        or not (path in GOVERNANCE_ALLOWED_EXACT or path.startswith(GOVERNANCE_ALLOWED_PREFIXES))
    ]
    if runtime_changed:
        blockers.append(f"governance compaction must not touch runtime/protected files: {runtime_changed}")


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

    for path in (DOC, STATE, STOP, MANIFEST, BACKLOG):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers, "warnings": warnings, "details": details}

    state = load_yaml(STATE)
    stop = load_yaml(STOP)
    changed = _changed_files()
    _validate_current_state(state, blockers)
    _validate_stop_conditions(stop, blockers)
    _validate_changed_files(changed, blockers)

    details["state"] = {
        "current_phase": state.get("current_phase"),
        "last_merged_pr": state.get("last_merged_pr"),
        "recommended_next_pr": state.get("recommended_next_pr"),
    }
    details["active_safety_gates"] = sorted(_as_strings(state.get("active_safety_gates")))
    details["protected_runtime_boundaries"] = sorted(_as_strings(state.get("protected_runtime_boundaries")))
    details["next_cleanup_candidates"] = sorted(_as_strings(state.get("next_cleanup_candidates")))
    details["changed_files"] = sorted(changed)
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "warnings": warnings, "details": details}


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Autonomous Development Loop Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
            "",
            "## Blockers",
            *(f"- {item}" for item in report["blockers"]),
        ]
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()
    report = build_report()
    _write_outputs(report, args.output_json, args.output_md)
    print(json.dumps({"overall": report["overall"], "ok": report["ok"], "blockers": report["blockers"]}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
