from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTTP_DIR = ROOT / "wecom_ability_service" / "http"
ADMIN_CONSOLE_DIR = ROOT / "wecom_ability_service" / "domains" / "admin_console"

# Historical exception that still exists before Wave 1 Step 2/3.
# The guardrail here is "no new controller requests dependency".
HTTP_REQUESTS_ALLOWLIST = {
    "wecom_ability_service/http/automation_conversion.py",
}

# Historical direct imports that still exist before the入口收口.
# This allowlist is intentionally explicit so any new direct dependency on
# legacy service wrappers fails immediately.
LEGACY_IMPORT_ALLOWLIST = {
    ("wecom_ability_service/http/admin_class_user.py", "services"),
    ("wecom_ability_service/http/admin_config.py", "services"),
    ("wecom_ability_service/http/admin_questionnaires.py", "services"),
    ("wecom_ability_service/http/admin_support.py", "services"),
    ("wecom_ability_service/http/admin_user_ops.py", "services"),
    ("wecom_ability_service/http/archive.py", "services"),
    ("wecom_ability_service/http/background_jobs.py", "services"),
    ("wecom_ability_service/http/callback_runtime.py", "services"),
    ("wecom_ability_service/http/contacts.py", "services"),
    ("wecom_ability_service/http/customer_automation.py", "customer_center.service"),
    ("wecom_ability_service/http/customer_automation.py", "customer_timeline.service"),
    ("wecom_ability_service/http/customer_automation.py", "services"),
    ("wecom_ability_service/http/customer_center.py", "customer_center.service"),
    ("wecom_ability_service/http/customer_timeline.py", "customer_timeline"),
    ("wecom_ability_service/http/identity.py", "services"),
    ("wecom_ability_service/http/ops.py", "services"),
    ("wecom_ability_service/http/ops_runtime.py", "services"),
    ("wecom_ability_service/http/public_questionnaires.py", "services"),
    ("wecom_ability_service/http/sidebar.py", "services"),
    ("wecom_ability_service/http/sync_jobs.py", "services"),
    ("wecom_ability_service/http/sync_support.py", "services"),
    ("wecom_ability_service/domains/admin_console/customer_profile_service.py", "customer_center.service"),
    ("wecom_ability_service/domains/admin_console/customer_profile_service.py", "services"),
    ("wecom_ability_service/domains/admin_console/service.py", "customer_center.service"),
    ("wecom_ability_service/domains/admin_console/service.py", "customer_timeline"),
    ("wecom_ability_service/domains/admin_console/service.py", "services"),
}

DIRECT_SQL_PATTERNS = (
    re.compile(r"\bget_db\s*\("),
    re.compile(r"\.execute\s*\("),
)


def _python_files(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.rglob("*.py")
        if path.name != "__init__.py" and "__pycache__" not in path.parts
    )


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _imports_requests(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "requests" or alias.name.startswith("requests."):
                    return True
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "requests" or module.startswith("requests."):
                return True
    return False


def _has_direct_sql(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")
    return any(pattern.search(source) for pattern in DIRECT_SQL_PATTERNS)


def _legacy_import_hits(path: Path) -> set[tuple[str, str]]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    hits: set[tuple[str, str]] = set()
    relative_path = _relative(path)

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        normalized_module = "." * node.level + (node.module or "")
        stripped_module = normalized_module.lstrip(".")
        if stripped_module in {
            "services",
            "customer_center",
            "customer_center.service",
            "customer_timeline",
            "customer_timeline.service",
        }:
            hits.add((relative_path, stripped_module))
            continue
        if stripped_module == "mcp_adapter":
            for alias in node.names:
                if alias.name.startswith("_"):
                    hits.add((relative_path, "mcp_adapter._private"))
    return hits


def test_http_controllers_do_not_add_requests_dependency():
    violations = {_relative(path) for path in _python_files(HTTP_DIR) if _imports_requests(path)}
    unexpected = violations - HTTP_REQUESTS_ALLOWLIST
    assert not unexpected, (
        "HTTP controllers must not add new requests dependency. "
        f"Unexpected files: {sorted(unexpected)}"
    )


def test_http_controllers_do_not_execute_sql_directly():
    violations = [_relative(path) for path in _python_files(HTTP_DIR) if _has_direct_sql(path)]
    assert not violations, (
        "HTTP controllers must not execute SQL directly. "
        f"Violations: {violations}"
    )


def test_legacy_service_imports_do_not_expand():
    observed: set[tuple[str, str]] = set()
    for directory in (HTTP_DIR, ADMIN_CONSOLE_DIR):
        for path in _python_files(directory):
            observed.update(_legacy_import_hits(path))

    unexpected = observed - LEGACY_IMPORT_ALLOWLIST
    assert not unexpected, (
        "Legacy direct-import baseline expanded. "
        "New imports must go through application services. "
        f"Unexpected entries: {sorted(unexpected)}"
    )

