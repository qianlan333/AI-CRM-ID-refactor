from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTTP_DIR = ROOT / "wecom_ability_service" / "http"
ADMIN_CONSOLE_DIR = ROOT / "wecom_ability_service" / "domains" / "admin_console"
CLASS_USER_CALLER_CUTOVER_FILES = [
    ROOT / "wecom_ability_service" / "http" / "admin_support.py",
    ROOT / "wecom_ability_service" / "domains" / "marketing_automation" / "service.py",
    ROOT / "wecom_ability_service" / "domains" / "user_ops" / "service.py",
]

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
    ("wecom_ability_service/http/admin_user_ops.py", "services"),
    ("wecom_ability_service/http/archive.py", "services"),
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
USER_OPS_POOL_PRIMITIVES = {
    "upsert_user_ops_lead_pool_member",
    "write_user_ops_lead_pool_history",
}


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
            "domains.identity.service",
            "domains.identity.repo",
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


def test_class_user_writer_callers_do_not_bypass_application_owner():
    forbidden_service_symbols = {
        "apply_class_user_status_change",
        "update_class_user_status_sync_result",
    }
    forbidden_primitive_calls = {
        "upsert_class_user_status_current(",
        "append_class_user_status_history(",
    }

    for path in CLASS_USER_CALLER_CUTOVER_FILES:
        source = path.read_text(encoding="utf-8")
        parsed = ast.parse(source, filename=str(path))

        for node in ast.walk(parsed):
            if not isinstance(node, ast.ImportFrom):
                continue
            stripped_module = ("." * node.level + (node.module or "")).lstrip(".")
            if stripped_module == "domains.class_user.service":
                raise AssertionError(f"{_relative(path)} must not import domains.class_user.service directly")
            if stripped_module == "services":
                forbidden = sorted(alias.name for alias in node.names if alias.name in forbidden_service_symbols)
                if forbidden:
                    raise AssertionError(
                        f"{_relative(path)} must not import legacy class_user service wrappers directly: {forbidden}"
                    )

        for fragment in forbidden_primitive_calls:
            assert fragment not in source, (
                f"{_relative(path)} must not call class_user write primitives directly: {fragment}"
            )


def test_background_jobs_and_sidebar_do_not_bypass_user_ops_application_owner():
    target_files = {
        "wecom_ability_service/http/background_jobs.py": {
            "required_fragments": ["application.user_ops"],
            "forbidden_service_symbols": {
                "schedule_user_ops_auto_assign_class_term_job",
                "run_due_user_ops_deferred_jobs",
                "refresh_contact_tags_for_external_userid",
                "refresh_user_ops_contact_tags_for_external_userid",
            },
        },
        "wecom_ability_service/http/sidebar.py": {
            "required_fragments": ["application.user_ops"],
            "forbidden_service_symbols": {
                "get_sidebar_lead_pool_status",
                "upsert_sidebar_lead_pool_class_term",
                "refresh_contact_tags_for_external_userid",
                "refresh_user_ops_contact_tags_for_external_userid",
            },
        },
    }

    for relative_path, config in target_files.items():
        path = ROOT / relative_path
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        imported_from_services: set[str] = set()
        imported_from_user_ops_domain = False

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = ("." * node.level + (node.module or "")).lstrip(".")
                if module == "services":
                    imported_from_services.update(alias.name for alias in node.names)
                if module in {"domains.user_ops", "domains.user_ops.service"}:
                    imported_from_user_ops_domain = True
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in {"wecom_ability_service.domains.user_ops", "wecom_ability_service.domains.user_ops.service"}:
                        imported_from_user_ops_domain = True

        forbidden = sorted(config["forbidden_service_symbols"] & imported_from_services)
        assert not forbidden, (
            f"{relative_path} must use application.user_ops owner instead of services.py for {forbidden}"
        )
        assert not imported_from_user_ops_domain, (
            f"{relative_path} must not import domains.user_ops.service directly"
        )
        for fragment in config["required_fragments"]:
            assert fragment in source, f"{relative_path} must import the formal user_ops application owner"


def test_admin_jobs_console_does_not_bypass_user_ops_application_owner():
    path = ROOT / "wecom_ability_service" / "domains" / "admin_jobs" / "service.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    imported_from_services: set[str] = set()
    imported_from_user_ops_domain = False
    forbidden_service_symbols = {
        "run_due_user_ops_deferred_jobs",
        "schedule_user_ops_auto_assign_class_term_job",
        "import_experience_leads",
        "import_mobile_class_term_source",
        "import_activation_status_source",
        "backfill_owner_class_terms_into_lead_pool",
        "refresh_user_ops_contact_tags_for_owner",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = ("." * node.level + (node.module or "")).lstrip(".")
            if module == "services":
                imported_from_services.update(alias.name for alias in node.names)
            if module in {"user_ops.service", "domains.user_ops.service"}:
                imported_from_user_ops_domain = True

    forbidden = sorted(forbidden_service_symbols & imported_from_services)
    assert not forbidden, (
        "wecom_ability_service/domains/admin_jobs/service.py must not import user_ops write wrappers "
        f"from services.py: {forbidden}"
    )
    assert not imported_from_user_ops_domain, (
        "wecom_ability_service/domains/admin_jobs/service.py must not import domains.user_ops.service directly"
    )
    assert "application.user_ops" in source, (
        "wecom_ability_service/domains/admin_jobs/service.py must import the formal user_ops application owner"
    )


def test_user_ops_pool_primitives_do_not_escape_outer_callers():
    extra_files = {
        ROOT / "wecom_ability_service" / "domains" / "admin_jobs" / "service.py",
    }
    target_paths = list(_python_files(HTTP_DIR)) + list(_python_files(ADMIN_CONSOLE_DIR)) + sorted(extra_files)
    violations: list[str] = []

    for path in target_paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        relative_path = _relative(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = ("." * node.level + (node.module or "")).lstrip(".")
            if module in {
                "services",
                "wecom_ability_service.services",
                "user_ops",
                "user_ops.service",
                "domains.user_ops",
                "domains.user_ops.service",
                "wecom_ability_service.domains.user_ops",
                "wecom_ability_service.domains.user_ops.service",
            }:
                forbidden = sorted(alias.name for alias in node.names if alias.name in USER_OPS_POOL_PRIMITIVES)
                if forbidden:
                    violations.append(f"{relative_path}: {forbidden}")

        assert "domains.user_ops.service.upsert_user_ops_lead_pool_member" not in source, (
            f"{relative_path} must not access user_ops pool-core primitive via module-qualified service path"
        )
        assert "domains.user_ops.service.write_user_ops_lead_pool_history" not in source, (
            f"{relative_path} must not access user_ops pool-core primitive via module-qualified service path"
        )

    assert not violations, (
        "Outer callers must not import user_ops pool-core primitives directly; "
        f"violations: {violations}"
    )
