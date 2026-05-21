#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONTRACT_FILES = [
    "aicrm_next/integration_gateway/media_contracts.py",
    "aicrm_next/integration_gateway/media_adapters.py",
    "aicrm_next/integration_gateway/audit.py",
    "aicrm_next/integration_gateway/idempotency.py",
]
REQUIRED_CLOUD_METHODS = ["put_object", "put_base64_object", "put_remote_reference", "get_public_reference", "delete_object"]
REQUIRED_WECOM_METHODS = ["upload_image", "upload_attachment", "resolve_media_id", "delete_or_expire_reference"]
DOCS_TO_SCAN = [
    "docs/d7_1_media_storage_wecom_media_adapter_contract.md",
    "docs/d7_1_media_adapter_implementation_report.md",
    "docs/d7_adapter_contract_catalog.md",
    "docs/d7_capability_readiness_matrix.md",
    "docs/d7_write_external_blocker_matrix.md",
    "docs/legacy_delete_batches.md",
    "docs/remaining_work_queue.md",
    "docs/go_no_go_checklist.md",
]
FORBIDDEN_MARKERS = ["production_ready", "production_approved", "delete_ready"]
PRODUCTION_CONFIG_PREFIXES = ("deploy/", ".github/")
PRODUCTION_CONFIG_KEYWORDS = ("nginx", "production", "systemd", "supervisor", "docker-compose")


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _class_methods(path: str, class_name: str) -> list[str]:
    tree = ast.parse(_read(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [child.name for child in node.body if isinstance(child, ast.FunctionDef)]
    return []


def _git_changed_files() -> list[str]:
    changed: set[str] = set()
    for cmd in (["git", "diff", "--name-only"], ["git", "diff", "--cached", "--name-only"], ["git", "ls-files", "--others", "--exclude-standard"]):
        try:
            result = subprocess.run(cmd, cwd=REPO_ROOT, check=True, capture_output=True, text=True)
        except Exception:
            continue
        changed.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return sorted(changed)


def _production_config_modified(changed_files: list[str]) -> bool:
    for path in changed_files:
        lower = path.lower()
        if lower.startswith(PRODUCTION_CONFIG_PREFIXES):
            return True
        if any(keyword in lower for keyword in PRODUCTION_CONFIG_KEYWORDS) and not lower.startswith(("docs/", "tests/", "tools/")):
            return True
    return False


def _check_adapter_runtime() -> dict[str, Any]:
    from aicrm_next.integration_gateway.audit import list_audit_events, reset_audit_events
    from aicrm_next.integration_gateway.idempotency import reset_idempotency_store
    from aicrm_next.integration_gateway.media_adapters import CloudStorageAdapter, WeComMediaAdapter

    reset_audit_events()
    reset_idempotency_store()
    cloud_a = CloudStorageAdapter("fake").put_base64_object(data_base64="ZmFrZQ==", file_name="fixture.png", content_type="image/png")
    cloud_b = CloudStorageAdapter("fake").put_base64_object(data_base64="ZmFrZQ==", file_name="fixture.png", content_type="image/png")
    wecom_a = WeComMediaAdapter("fake").upload_image(data_base64="ZmFrZQ==", file_name="fixture.png")
    wecom_b = WeComMediaAdapter("fake").upload_image(data_base64="ZmFrZQ==", file_name="fixture.png")
    disabled = CloudStorageAdapter("disabled").put_base64_object(data_base64="ZmFrZQ==", file_name="fixture.png", content_type="image/png")
    guarded = WeComMediaAdapter("production").upload_image(data_base64="ZmFrZQ==", file_name="fixture.png")
    staging = CloudStorageAdapter("staging").put_remote_reference(source_url="https://example.invalid/a.png", file_name="remote.png", content_type="image/png")
    events = list_audit_events()
    return {
        "fake_cloud_deterministic": cloud_a["storage_key"] == cloud_b["storage_key"],
        "fake_wecom_deterministic": wecom_a["media_id"] == wecom_b["media_id"],
        "disabled_error": disabled["ok"] is False and disabled["error_code"] == "adapter_disabled",
        "production_guard": guarded["ok"] is False and guarded["error_code"] in {"production_guard_failed", "production_not_implemented"},
        "side_effect_safety": all(item["side_effect_executed"] is False for item in [cloud_a, cloud_b, wecom_a, wecom_b, disabled, guarded, staging]),
        "audit_events_created": len(events) >= 7 and all(event.get("audit_id") for event in events),
    }


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    missing_files = [path for path in CONTRACT_FILES + DOCS_TO_SCAN if not (REPO_ROOT / path).exists()]
    if missing_files:
        blockers.append("missing D7.1 files: " + ", ".join(missing_files))

    adapter_contracts = {
        "CloudStorageAdapter": _class_methods("aicrm_next/integration_gateway/media_adapters.py", "CloudStorageAdapter") if (REPO_ROOT / "aicrm_next/integration_gateway/media_adapters.py").exists() else [],
        "WeComMediaAdapter": _class_methods("aicrm_next/integration_gateway/media_adapters.py", "WeComMediaAdapter") if (REPO_ROOT / "aicrm_next/integration_gateway/media_adapters.py").exists() else [],
    }
    missing_cloud_methods = [method for method in REQUIRED_CLOUD_METHODS if method not in adapter_contracts["CloudStorageAdapter"]]
    missing_wecom_methods = [method for method in REQUIRED_WECOM_METHODS if method not in adapter_contracts["WeComMediaAdapter"]]
    if missing_cloud_methods:
        blockers.append("CloudStorageAdapter missing methods: " + ", ".join(missing_cloud_methods))
    if missing_wecom_methods:
        blockers.append("WeComMediaAdapter missing methods: " + ", ".join(missing_wecom_methods))

    adapter_source = _read("aicrm_next/integration_gateway/media_adapters.py") if (REPO_ROOT / "aicrm_next/integration_gateway/media_adapters.py").exists() else ""
    mode_guards = {
        "default_cloud_mode_fake": "AICRM_NEXT_MEDIA_STORAGE_MODE\", \"fake\"" in adapter_source,
        "default_wecom_mode_fake": "AICRM_NEXT_WECOM_MEDIA_MODE\", \"fake\"" in adapter_source,
        "real_cloud_env_guard": "AICRM_NEXT_ENABLE_REAL_CLOUD_STORAGE" in adapter_source,
        "real_wecom_env_guard": "AICRM_NEXT_ENABLE_REAL_WECOM_MEDIA" in adapter_source,
        "production_fail_closed": "production_guard_failed" in adapter_source and "production_not_implemented" in adapter_source,
    }
    if not all(mode_guards.values()):
        blockers.append("adapter mode guards incomplete")

    runtime = _check_adapter_runtime()
    if not all(runtime.values()):
        blockers.append("adapter runtime safety check failed")

    app_source = _read("aicrm_next/media_library/application.py") if (REPO_ROOT / "aicrm_next/media_library/application.py").exists() else ""
    media_boundary = {
        "from_base64_uses_adapter": "put_base64_object" in app_source and "upload_image" in app_source,
        "from_url_uses_remote_reference": "put_remote_reference" in app_source and "resolve_media_id" in app_source,
        "no_remote_fetch": "httpx" not in app_source and "requests." not in app_source,
    }
    if not all(media_boundary.values()):
        blockers.append("Media Library adapter boundary incomplete")

    docs_text = "\n".join(_read(path) for path in DOCS_TO_SCAN if (REPO_ROOT / path).exists())
    forbidden_status_markers = [marker for marker in FORBIDDEN_MARKERS if marker in docs_text]
    if forbidden_status_markers:
        blockers.append("forbidden status markers: " + ", ".join(forbidden_status_markers))

    changed_files = _git_changed_files()
    production_config_modified = _production_config_modified(changed_files)
    if production_config_modified:
        blockers.append("production/deploy config modified")

    media_smoke = {"ok": all(token in _read("aicrm_next/media_library/api.py") for token in ["/api/admin/image-library", "/api/admin/attachment-library", "/api/admin/miniprogram-library"])}
    media_parity = {"ok": (REPO_ROOT / "experiments/ai_crm_next/tools/compare_media_library_parity.py").exists()}

    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "adapter_contracts": adapter_contracts,
        "mode_guards": mode_guards,
        "idempotency": {"deterministic_fake_results": runtime["fake_cloud_deterministic"] and runtime["fake_wecom_deterministic"]},
        "audit": {"audit_events_created": runtime["audit_events_created"]},
        "side_effect_safety": {"side_effect_executed_false": runtime["side_effect_safety"]},
        "media_smoke": media_smoke,
        "media_parity": media_parity,
        "forbidden_status_markers": forbidden_status_markers,
        "production_config_modified": production_config_modified,
        "changed_files": changed_files,
        "recommendation": "READY_FOR_D7_1_ACCEPTANCE" if not blockers else "FIX_D7_1_MEDIA_ADAPTER_BLOCKERS",
    }


def write_markdown(report: dict[str, Any], output: Path) -> None:
    lines = [
        "# D7.1 Media Adapter Contract Check",
        "",
        f"- ok: `{str(report['ok']).lower()}`",
        f"- recommendation: `{report['recommendation']}`",
        f"- production_config_modified: `{str(report['production_config_modified']).lower()}`",
        "",
        "## Blockers",
    ]
    lines.extend([f"- {item}" for item in report["blockers"]] or ["- none"])
    for section in ("adapter_contracts", "mode_guards", "idempotency", "audit", "side_effect_safety", "media_smoke", "media_parity"):
        lines.extend(["", f"## {section}", "", "```json", json.dumps(report[section], ensure_ascii=False, indent=2), "```"])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check D7.1 Media storage / WeCom media adapter contract.")
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()
    report = build_report()
    Path(args.output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, Path(args.output_md))
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print("overall:", "PASS" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
