#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CHECKERS = [
    {
        "name": "architecture_skill_compliance",
        "module": "tools.check_architecture_skill_compliance",
        "function": "build_report",
        "critical": True,
    },
    {
        "name": "architecture_doc_consistency",
        "module": "tools.check_architecture_doc_consistency",
        "function": "build_report",
        "critical": True,
    },
    {
        "name": "route_ownership_manifest",
        "module": "tools.check_production_route_ownership_manifest",
        "function": "build_report",
        "critical": True,
    },
    {
        "name": "production_route_resolution",
        "module": "tools.check_production_route_resolution",
        "function": "run_check",
        "critical": True,
    },
    {
        "name": "repository_provider_hardening",
        "module": "tools.check_repository_provider_hardening",
        "function": "run_check",
        "critical": True,
    },
    {
        "name": "admin_read_model_boundary",
        "module": "tools.check_admin_read_model_boundary",
        "function": "run_check",
        "critical": True,
    },
    {
        "name": "admin_real_data_binding",
        "module": "tools.check_admin_pages_real_data_binding",
        "function": "run_check",
        "critical": True,
    },
    {
        "name": "production_runtime_gaps",
        "module": "tools.check_next_production_runtime_gaps",
        "function": "run_check",
        "critical": True,
    },
    {
        "name": "timer_route_readiness",
        "module": "tools.check_next_timer_route_readiness",
        "function": "run_check",
        "critical": False,
    },
]

MUST_BLOCK_ON_FAILURE = {
    "architecture_skill_compliance",
    "production_route_resolution",
    "repository_provider_hardening",
}


def _load_runner(module_name: str, function_name: str) -> Callable[[], dict[str, Any]]:
    module = importlib.import_module(module_name)
    runner = getattr(module, function_name)
    return runner


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _result_blockers(name: str, result: dict[str, Any]) -> list[str]:
    blockers = [str(item) for item in _as_list(result.get("blockers"))]
    for key in (
        "route_404_blockers",
        "content_blockers",
        "oauth_blockers",
        "data_blockers",
        "bad_marker_hits",
        "auth_failures",
        "placeholder_pages",
        "empty_data_pages",
    ):
        blockers.extend(f"{key}:{item}" for item in _as_list(result.get(key)))
    if result.get("production_config_modified"):
        blockers.append("production_config_modified")
    if result.get("ok") is False and not blockers:
        blockers.append(f"{name}_failed_without_blocker_details")
    return blockers


def _run_checker(checker: dict[str, Any]) -> dict[str, Any]:
    name = str(checker["name"])
    try:
        runner = _load_runner(str(checker["module"]), str(checker["function"]))
        result = runner()
        if not isinstance(result, dict):
            return {
                "ok": False,
                "blockers": [f"{name}_returned_non_dict_result"],
                "warnings": [],
            }
        return result
    except Exception as exc:  # pragma: no cover - defensive aggregation path
        return {
            "ok": False,
            "blockers": [f"{name}_raised_exception:{exc}"],
            "warnings": [],
            "traceback": traceback.format_exc(),
        }


def _canary_evidence_present() -> bool:
    # Local checker output is deliberately not accepted as production canary
    # evidence. A future server-side verifier can set a dedicated, audited
    # evidence flag and include remote SHA/header details.
    return os.getenv("AICRM_MAINLINE_SERVER_CANARY_EVIDENCE") == "verified_server_evidence"


def collect_checker_results() -> dict[str, dict[str, Any]]:
    return {str(checker["name"]): _run_checker(checker) for checker in CHECKERS}


def build_report(checker_results: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    results = checker_results or collect_checker_results()
    blockers: list[str] = []
    warnings: list[str] = []

    checker_names = {str(checker["name"]) for checker in CHECKERS}
    missing = sorted(checker_names - set(results))
    for name in missing:
        blockers.append(f"{name}:missing_checker_result")

    for checker in CHECKERS:
        name = str(checker["name"])
        result = results.get(name) or {}
        result_blockers = _result_blockers(name, result)
        result_warnings = [str(item) for item in _as_list(result.get("warnings"))]
        critical = bool(checker.get("critical"))
        if result.get("ok") is False and critical:
            blockers.extend(f"{name}:{item}" for item in result_blockers)
        elif result.get("ok") is False:
            warnings.extend(f"{name}:{item}" for item in result_blockers)
        warnings.extend(f"{name}:{item}" for item in result_warnings)

    for name in MUST_BLOCK_ON_FAILURE:
        result = results.get(name) or {}
        if result.get("ok") is not True:
            blockers.append(f"{name}:required_checker_not_ok")

    route_resolution = results.get("production_route_resolution") or {}
    if not route_resolution:
        blockers.append("production_route_resolution:missing")
    if route_resolution.get("shadowed_exact_routes"):
        blockers.append("production_route_resolution:shadowed_exact_routes_present")

    timer_result = results.get("timer_route_readiness") or {}
    production_canary_evidence_present = _canary_evidence_present()
    safe_to_enable_timers = bool(timer_result.get("safe_to_enable_timers")) and production_canary_evidence_present
    safe_to_remove_legacy_fallback = False
    safe_to_enable_real_external_calls = False

    if timer_result.get("safe_to_enable_timers") and not production_canary_evidence_present:
        warnings.append("timer_route_readiness:local_timer_success_is_not_production_canary_evidence")
    if not production_canary_evidence_present:
        warnings.append("production_canary_evidence:absent_or_not_server_verified")

    normalized_results = {
        name: {
            "ok": result.get("ok"),
            "blockers": _result_blockers(name, result),
            "warnings": [str(item) for item in _as_list(result.get("warnings"))],
            "safe_to_enable_timers": result.get("safe_to_enable_timers"),
            "shadowed_exact_routes": result.get("shadowed_exact_routes"),
        }
        for name, result in results.items()
    }

    return {
        "ok": not blockers,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "checker_results": normalized_results,
        "safe_to_enable_timers": safe_to_enable_timers,
        "safe_to_remove_legacy_fallback": safe_to_remove_legacy_fallback,
        "safe_to_enable_real_external_calls": safe_to_enable_real_external_calls,
        "production_canary_evidence_present": production_canary_evidence_present,
    }


def write_outputs(result: dict[str, Any], output_md: str | None, output_json: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Mainline Architecture Guardrails",
            "",
            f"- ok: `{str(result['ok']).lower()}`",
            f"- blockers: `{len(result['blockers'])}`",
            f"- warnings: `{len(result['warnings'])}`",
            f"- safe_to_enable_timers: `{str(result['safe_to_enable_timers']).lower()}`",
            f"- safe_to_remove_legacy_fallback: `{str(result['safe_to_remove_legacy_fallback']).lower()}`",
            f"- safe_to_enable_real_external_calls: `{str(result['safe_to_enable_real_external_calls']).lower()}`",
            f"- production_canary_evidence_present: `{str(result['production_canary_evidence_present']).lower()}`",
            "",
            "## Checker Results",
        ]
        for name, payload in result["checker_results"].items():
            lines.append(
                f"- {name}: ok=`{payload.get('ok')}` blockers=`{len(payload.get('blockers') or [])}` "
                f"warnings=`{len(payload.get('warnings') or [])}`"
            )
        lines.extend(["", "## Blockers"])
        lines.extend(f"- {item}" for item in result["blockers"])
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {item}" for item in result["warnings"])
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate AI-CRM Next mainline architecture guardrails.")
    parser.add_argument("--output-md", default="")
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()
    result = build_report()
    write_outputs(result, args.output_md, args.output_json)
    print(json.dumps({"ok": result["ok"], "blockers": result["blockers"], "warnings": result["warnings"]}, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
