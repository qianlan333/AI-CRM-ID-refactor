#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import generate_gray_release_report  # noqa: E402

Json = dict[str, Any]


@dataclass(frozen=True)
class BatchDefinition:
    name: str
    included_routes: tuple[str, ...]
    excluded_routes: tuple[str, ...]
    route_flags: Json


MEDIA_READONLY_BATCH = BatchDefinition(
    name="media_readonly",
    included_routes=(
        "GET /admin/image-library",
        "GET /api/admin/image-library",
        "GET /admin/attachment-library",
        "GET /api/admin/attachment-library",
        "GET /admin/miniprogram-library",
        "GET /api/admin/miniprogram-library",
    ),
    excluded_routes=(
        "POST /api/admin/image-library",
        "POST /api/admin/image-library/from-url",
        "POST /api/admin/image-library/from-base64",
        "PUT /api/admin/image-library/{image_id}",
        "DELETE /api/admin/image-library/{image_id}",
        "POST /api/admin/attachment-library",
        "PUT /api/admin/attachment-library/{attachment_id}",
        "DELETE /api/admin/attachment-library/{attachment_id}",
        "POST /api/admin/miniprogram-library",
        "PUT /api/admin/miniprogram-library/{item_id}",
        "DELETE /api/admin/miniprogram-library/{item_id}",
    ),
    route_flags={
        "AICRM_NEXT_ROUTE_MEDIA_READONLY": True,
        "AICRM_NEXT_ROUTE_MEDIA_WRITES": False,
        "AICRM_NEXT_EXTERNAL_CLOUD_STORAGE": False,
        "AICRM_NEXT_EXTERNAL_WECOM_MEDIA": False,
    },
)

BATCHES = {MEDIA_READONLY_BATCH.name: MEDIA_READONLY_BATCH}
MEDIA_PAGE_ROUTES = {"/admin/image-library", "/admin/attachment-library", "/admin/miniprogram-library"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Json:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected object JSON: {path}")
    return payload


def _write_json(path: Path, payload: Json) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_command(command: list[str], *, cwd: Path) -> Json:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "ok": completed.returncode == 0,
    }


def _validate_batch(batch: BatchDefinition) -> list[Json]:
    blockers: list[Json] = []
    forbidden_included = ("POST ", "PUT ", "PATCH ", "DELETE ")
    for route in batch.included_routes:
        if route.startswith(forbidden_included):
            blockers.append({"reason": "write_route_included", "route": route})
    for fragment in ("from-url", "from-base64", "checkout", "notify", "wecom", "cloud"):
        if any(fragment in route.lower() for route in batch.included_routes):
            blockers.append({"reason": "forbidden_fragment_in_included_routes", "fragment": fragment})
    return blockers


def _screenshot_baseline_result(route_status_path: Path) -> Json:
    if not route_status_path.exists():
        return {"ok": False, "reason": "route_status_missing", "path": str(route_status_path)}
    payload = _load_json(route_status_path)
    route_results = payload.get("route_results")
    if not isinstance(route_results, list):
        return {"ok": False, "reason": "route_results_missing", "path": str(route_status_path)}
    indexed = {item.get("route"): item for item in route_results if isinstance(item, dict)}
    missing = sorted(route for route in MEDIA_PAGE_ROUTES if route not in indexed)
    failed = sorted(route for route in MEDIA_PAGE_ROUTES if route in indexed and not indexed[route].get("ok"))
    return {
        "ok": not missing and not failed,
        "route_status_path": str(route_status_path),
        "required_routes": sorted(MEDIA_PAGE_ROUTES),
        "missing_routes": missing,
        "failed_routes": failed,
        "summary": payload.get("summary", {}),
    }


def _request_old_gets(old_base_url: str, included_routes: tuple[str, ...]) -> list[Json]:
    import httpx

    results: list[Json] = []
    with httpx.Client(timeout=10.0, follow_redirects=False) as client:
        for route in included_routes:
            method, path = route.split(" ", 1)
            if method != "GET":
                raise RuntimeError(f"old-base-url rehearsal refuses non-GET route: {route}")
            response = client.get(old_base_url.rstrip("/") + path)
            results.append({"method": method, "path": path, "status_code": response.status_code, "ok": response.status_code < 500})
    return results


def _rollback_dry_run(batch: BatchDefinition) -> Json:
    return {
        "route_flag_rollback_instruction": "AICRM_NEXT_ROUTE_MEDIA_READONLY=false",
        "expected_owner_after_rollback": "old Flask",
        "rollback_verified": "dry-run only",
        "production_config_modified": False,
        "notes": "No proxy or production config was changed during this rehearsal.",
    }


def _side_effect_safety(smoke_report: Json) -> Json:
    smoke_safety = smoke_report.get("side_effect_safety") if isinstance(smoke_report.get("side_effect_safety"), dict) else {}
    return {
        "production_config_modified": False,
        "old_write_endpoints_executed": bool(smoke_safety.get("old_write_endpoints_executed", False)),
        "cloud_storage_upload_executed": bool(smoke_safety.get("external_upload_executed", False)),
        "wecom_media_upload_executed": bool(smoke_safety.get("wecom_media_upload_executed", False)),
        "real_traffic_cutover_executed": False,
        "default_endpoints_get_only": bool(smoke_safety.get("default_endpoints_get_only", False)),
    }


def run_rehearsal(args: argparse.Namespace) -> Json:
    if args.batch not in BATCHES:
        return {
            "ok": False,
            "batch": args.batch,
            "mode": "local_rehearsal",
            "blockers": [{"reason": "unsupported_batch", "supported_batches": sorted(BATCHES)}],
            "warnings": [],
            "skipped": [],
        }
    batch = BATCHES[args.batch]
    blockers = _validate_batch(batch)
    warnings: list[Json] = []
    skipped: list[Json] = []

    if not args.next_testclient and not args.next_base_url:
        blockers.append({"reason": "missing_next_target", "message": "Use --next-testclient or --next-base-url."})

    output_json = Path(args.output_json)
    work_dir = output_json.parent if output_json.parent != Path("") else Path("/tmp")
    smoke_json = work_dir / f"{output_json.stem}.media_smoke.json"
    smoke_md = work_dir / f"{output_json.stem}.media_smoke.md"
    parity_json = work_dir / f"{output_json.stem}.media_parity.json"
    parity_md = work_dir / f"{output_json.stem}.media_parity.md"
    aggregate_json = work_dir / f"{output_json.stem}.aggregate.json"
    aggregate_md = work_dir / f"{output_json.stem}.aggregate.md"

    smoke_command = [sys.executable, "tools/media_library_gray_smoke.py", "--output-md", str(smoke_md), "--output-json", str(smoke_json)]
    if args.next_testclient:
        smoke_command.insert(2, "--next-testclient")
    else:
        smoke_command[2:2] = ["--next-base-url", args.next_base_url]
    parity_command = [
        sys.executable,
        "tools/compare_media_library_parity.py",
        "--old-fixture-dir",
        "tests/fixtures/old_media_library",
        "--next-testclient",
        "--output-md",
        str(parity_md),
        "--output-json",
        str(parity_json),
    ]

    smoke_command_result = _run_command(smoke_command, cwd=PROJECT_ROOT) if not blockers else {"ok": False, "skipped": True}
    parity_command_result = _run_command(parity_command, cwd=PROJECT_ROOT) if not blockers else {"ok": False, "skipped": True}

    smoke_report: Json = {}
    parity_report: Json = {}
    aggregate_report: Json = {}
    if smoke_command_result.get("ok") and smoke_json.exists():
        smoke_report = _load_json(smoke_json)
    else:
        blockers.append({"reason": "media_gray_smoke_failed", "command_result": smoke_command_result})
    if parity_command_result.get("ok") and parity_json.exists():
        parity_report = _load_json(parity_json)
    else:
        blockers.append({"reason": "media_parity_failed", "command_result": parity_command_result})
    if smoke_report and parity_report:
        aggregate_report = generate_gray_release_report.build_report(args.batch, str(smoke_json), str(parity_json))
        generate_gray_release_report.write_markdown_report(aggregate_report, str(aggregate_md))
        generate_gray_release_report.write_json_report(aggregate_report, str(aggregate_json))
        blockers.extend(aggregate_report.get("blockers") or [])
        warnings.extend(aggregate_report.get("warnings") or [])
        skipped.extend(aggregate_report.get("skipped") or [])

    screenshot_result = _screenshot_baseline_result(PROJECT_ROOT / "artifacts" / "frontend_screenshots" / "route_status.json")
    if not screenshot_result["ok"]:
        blockers.append({"reason": "screenshot_baseline_missing_or_failed", "result": screenshot_result})

    old_route_results: list[Json] = []
    if args.old_base_url:
        try:
            old_route_results = _request_old_gets(args.old_base_url, batch.included_routes)
        except Exception as exc:
            blockers.append({"reason": "old_get_rehearsal_failed", "message": str(exc)})
    else:
        skipped.append({"reason": "old_base_url_not_provided", "message": "No old Flask GET comparison requested for this local rehearsal."})

    safety = _side_effect_safety(smoke_report)
    safety_blockers = [key for key, value in safety.items() if key.endswith("_executed") and value is True]
    for key in safety_blockers:
        blockers.append({"reason": "side_effect_safety_violation", "field": key})

    report = {
        "ok": not blockers,
        "batch": args.batch,
        "mode": "local_rehearsal",
        "run_time": _utc_now(),
        "route_flags": batch.route_flags,
        "included_routes": list(batch.included_routes),
        "excluded_routes": list(batch.excluded_routes),
        "route_results": smoke_report.get("route_results", []),
        "old_route_results": old_route_results,
        "smoke_result": {
            "command": smoke_command,
            "command_ok": smoke_command_result.get("ok"),
            "report_json": str(smoke_json),
            "ok": smoke_report.get("ok"),
        },
        "parity_result": {
            "command": parity_command,
            "command_ok": parity_command_result.get("ok"),
            "report_json": str(parity_json),
            "overall": parity_report.get("overall"),
            "ok": parity_report.get("ok") is True or parity_report.get("overall") == "PASS",
        },
        "screenshot_baseline_result": screenshot_result,
        "gray_release_report": {
            "markdown": str(aggregate_md),
            "json": str(aggregate_json),
            "recommendation": aggregate_report.get("go_no_go_recommendation"),
        },
        "side_effect_safety": safety,
        "rollback_dry_run": _rollback_dry_run(batch),
        "signoff_reference": "docs/gray_release_signoff_template.md",
        "blockers": blockers,
        "warnings": warnings,
        "skipped": skipped,
        "recommendation": "GO" if not blockers else "NO_GO",
    }
    return report


def write_json_report(report: Json, path: Path) -> None:
    _write_json(path, report)


def write_markdown_report(report: Json, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Gray Rehearsal Batch Report",
        "",
        f"- batch: `{report['batch']}`",
        f"- mode: `{report['mode']}`",
        f"- run_time: `{report['run_time']}`",
        f"- overall: `{'PASS' if report['ok'] else 'FAIL'}`",
        f"- recommendation: `{report['recommendation']}`",
        f"- signoff_reference: `{report['signoff_reference']}`",
        "",
        "## Route Flags",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in report["route_flags"].items())
    lines.extend(["", "## Included Routes"])
    lines.extend(f"- `{route}`" for route in report["included_routes"])
    lines.extend(["", "## Excluded Routes"])
    lines.extend(f"- `{route}`" for route in report["excluded_routes"])
    lines.extend(["", "## Side Effect Safety"])
    lines.extend(f"- {key}: `{value}`" for key, value in sorted(report["side_effect_safety"].items()))
    lines.extend(["", "## Rollback Dry Run"])
    for key, value in report["rollback_dry_run"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Blockers"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["blockers"]] or ["- none"])
    lines.extend(["", "## Warnings"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["warnings"]] or ["- none"])
    lines.extend(["", "## Skipped"])
    lines.extend([f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["skipped"]] or ["- none"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local route-level gray release rehearsal batch.")
    parser.add_argument("--batch", required=True)
    parser.add_argument("--next-testclient", action="store_true")
    parser.add_argument("--next-base-url", default="")
    parser.add_argument("--old-base-url", default="", help="Optional old Flask base URL; only GET routes are requested.")
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_rehearsal(args)
    write_markdown_report(report, Path(args.output_md))
    write_json_report(report, Path(args.output_json))
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print("overall:", "PASS" if report["ok"] else "FAIL")
    print("recommendation:", report["recommendation"])
    for key, value in sorted(report["side_effect_safety"].items()):
        print(f"{key}: {value}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
