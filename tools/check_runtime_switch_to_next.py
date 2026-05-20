from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
FORBIDDEN_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+(wecom_ability_service|openclaw_service)\b|import\s+(wecom_ability_service|openclaw_service)\b)"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _scan_forbidden_imports(package_dir: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in sorted(package_dir.rglob("*.py")):
        for lineno, line in enumerate(_read(path).splitlines(), start=1):
            if FORBIDDEN_IMPORT_RE.search(line):
                findings.append(
                    {
                        "path": str(path.relative_to(REPO_ROOT)),
                        "line": lineno,
                        "text": line.strip(),
                    }
                )
    return findings


def _check_next_route_owner() -> dict[str, Any]:
    try:
        from fastapi.testclient import TestClient

        from aicrm_next.main import app

        response = TestClient(app).get("/health")
        return {
            "ok": response.status_code == 200 and response.headers.get("X-AICRM-Route-Owner") == "ai_crm_next",
            "status_code": response.status_code,
            "route_owner": response.headers.get("X-AICRM-Route-Owner", ""),
            "app": response.headers.get("X-AICRM-App", ""),
        }
    except Exception as exc:  # pragma: no cover - exercised by CLI smoke
        return {"ok": False, "error": str(exc)}


def _check_legacy_route_owner_contract() -> dict[str, Any]:
    legacy_init = REPO_ROOT / "wecom_ability_service" / "__init__.py"
    if not legacy_init.exists():
        return {"ok": False, "error": "wecom_ability_service/__init__.py missing"}
    content = _read(legacy_init)
    return {
        "ok": "X-AICRM-Route-Owner" in content and "legacy_flask" in content,
        "route_owner": "legacy_flask" if "legacy_flask" in content else "",
        "app": "ai_crm_legacy_flask" if "ai_crm_legacy_flask" in content else "",
        "mode": "static_contract",
    }


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    app_py = REPO_ROOT / "app.py"
    app_content = _read(app_py) if app_py.exists() else ""
    legacy_runner = REPO_ROOT / "legacy_flask_app.py"
    next_package = REPO_ROOT / "aicrm_next"
    runtime_doc = REPO_ROOT / "docs" / "runtime_switch_to_next.md"

    default_runtime_ok = (
        "NEXT_APP_IMPORT = \"aicrm_next.main:app\"" in app_content
        and "uvicorn.run(NEXT_APP_IMPORT" in app_content
        and "run-legacy" in app_content
    )
    if not default_runtime_ok:
        blockers.append("app.py does not clearly default to AI-CRM Next with legacy fallback")

    if not legacy_runner.exists():
        blockers.append("legacy_flask_app.py missing")

    if not next_package.exists():
        blockers.append("root aicrm_next package missing")

    if not runtime_doc.exists():
        blockers.append("docs/runtime_switch_to_next.md missing")

    forbidden_imports = _scan_forbidden_imports(next_package) if next_package.exists() else []
    if forbidden_imports:
        blockers.append("aicrm_next imports legacy backend packages")

    next_headers = _check_next_route_owner() if next_package.exists() else {"ok": False, "error": "missing"}
    if not next_headers.get("ok"):
        blockers.append("AI-CRM Next route owner header check failed")

    legacy_headers = _check_legacy_route_owner_contract()
    if not legacy_headers.get("ok"):
        blockers.append("legacy Flask route owner header contract missing")

    report = {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "default_runtime": {
            "command": "python3 app.py run",
            "runtime": "ai_crm_next",
            "app_import": "aicrm_next.main:app",
            "ok": default_runtime_ok,
        },
        "legacy_fallback": {
            "commands": ["python3 app.py run-legacy", "python3 legacy_flask_app.py run"],
            "exists": legacy_runner.exists(),
        },
        "route_owner_headers": {
            "next": next_headers,
            "legacy": legacy_headers,
        },
        "forbidden_imports": forbidden_imports,
        "recommendation": "READY_FOR_RUNTIME_SWITCH_ACCEPTANCE" if not blockers else "FIX_BLOCKERS",
    }
    return report


def _write_markdown(report: dict[str, Any], output: Path) -> None:
    lines = [
        "# Runtime Switch To AI-CRM Next Check",
        "",
        f"- ok: `{str(report['ok']).lower()}`",
        f"- recommendation: `{report['recommendation']}`",
        f"- default_runtime: `{report['default_runtime']['runtime']}` via `{report['default_runtime']['command']}`",
        f"- legacy_fallback: `{', '.join(report['legacy_fallback']['commands'])}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend([f"- {item}" for item in report["blockers"]] or ["- none"])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {item}" for item in report["warnings"]] or ["- none"])
    lines.extend(
        [
            "",
            "## Route Owner Headers",
            "",
            f"- next: `{report['route_owner_headers']['next']}`",
            f"- legacy: `{report['route_owner_headers']['legacy']}`",
            "",
            "## Forbidden Imports",
            "",
        ]
    )
    lines.extend([f"- {item}" for item in report["forbidden_imports"]] or ["- none"])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check that AI-CRM defaults to AI-CRM Next with legacy fallback.")
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    report = build_report()
    Path(args.output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_markdown(report, Path(args.output_md))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
