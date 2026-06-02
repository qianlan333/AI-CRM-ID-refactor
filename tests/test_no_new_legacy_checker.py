from __future__ import annotations

from pathlib import Path

from scripts.check_no_new_legacy import (
    check_customer_read_model_legacy_deletion,
    check_messages_broad_wildcard_deletion,
    check_sidebar_readonly_closeout_lock,
    scan_source_tree,
)


def test_no_new_legacy_checker_flags_disallowed_legacy_import(tmp_path: Path) -> None:
    target = tmp_path / "aicrm_next/new_api.py"
    target.parent.mkdir()
    target.write_text("from aicrm_next.integration_gateway.legacy_flask_facade import forward_to_legacy_flask\n", encoding="utf-8")

    violations = scan_source_tree(tmp_path)

    assert [violation.code for violation in violations] == ["legacy_flask_facade_import"]
    payload = violations[0].to_dict()
    assert payload["path"] == "aicrm_next/new_api.py"
    assert "route registry" in payload["remediation"]


def test_no_new_legacy_checker_exempts_tests_and_docs(tmp_path: Path) -> None:
    docs = tmp_path / "docs/note.py"
    tests = tmp_path / "tests/test_note.py"
    docs.parent.mkdir()
    tests.parent.mkdir()
    docs.write_text("from wecom_ability_service.db import get_db\n", encoding="utf-8")
    tests.write_text("from aicrm_next.integration_gateway.legacy_flask_facade import forward_to_legacy_flask\n", encoding="utf-8")

    assert scan_source_tree(tmp_path) == []


def test_customer_read_model_legacy_deletion_guard_flags_deleted_patterns(tmp_path: Path) -> None:
    crm = tmp_path / "aicrm_next/customer_read_model/application.py"
    script = tmp_path / "scripts/backfill_customer_read_model.py"
    crm.parent.mkdir(parents=True)
    script.parent.mkdir(parents=True)
    crm.write_text(
        "from aicrm_next.integration_gateway.legacy_customer_read_facade import get_customer_via_legacy\n"
        "CUSTOMER_READ_MODEL" + "_LEGACY_ROLLBACK_ENABLED = '1'\n"
        "LegacyShadowCustomerReadModelSource\n",
        encoding="utf-8",
    )
    script.write_text("target = get_settings().database_url\nsource = 'legacy-shadow'\n", encoding="utf-8")

    violations = check_customer_read_model_legacy_deletion(tmp_path)
    codes = {violation.code for violation in violations}

    assert "customer_read_legacy_facade_import" in codes
    assert "customer_read_legacy_rollback_flag" in codes
    assert "customer_read_legacy_shadow_source" in codes
    assert "customer_read_backfill_execute_uses_default_database" in codes
    assert "customer_read_backfill_legacy_source" in codes


def test_messages_broad_wildcard_deletion_guard_flags_legacy_forward_and_bad_lifecycle(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text(
        "from aicrm_next.integration_gateway.legacy_flask_facade import forward_to_legacy_flask\n"
        '@wildcard_router.api_route("/api/messages/{path:path}", methods=_ALL_METHODS)\n'
        "async def legacy_production_compat_routes(request):\n"
        "    return await forward_to_legacy_flask(request)\n",
        encoding="utf-8",
    )
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/messages*\n"
        "    runtime_owner: production_compat\n"
        "    legacy_fallback_allowed: true\n"
        "    delete_status: active\n"
        "    replacement_status: validating\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/messages*\n"
        "    current_runtime_owner: production_compat\n"
        "    production_behavior: legacy_forward\n"
        "    legacy_fallback_allowed: true\n"
        "    delete_ready: false\n",
        encoding="utf-8",
    )

    violations = check_messages_broad_wildcard_deletion(tmp_path)
    codes = {violation.code for violation in violations}

    assert "messages_broad_wildcard_decorator" in codes
    assert "messages_broad_wildcard_legacy_forward" in codes
    assert "messages_broad_wildcard_registry_legacy_allowed" in codes
    assert "messages_broad_wildcard_registry_delete_status" in codes
    assert "messages_broad_wildcard_registry_replacement_status" in codes
    assert "messages_broad_wildcard_manifest_legacy_forward" in codes


def test_messages_broad_wildcard_deletion_guard_allows_exact_routes(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text(
        '@router.get("/api/messages/{external_userid}")\n'
        '@router.get("/api/messages/{external_userid}/recent")\n'
        '@router.get("/api/messages/search")\n'
        "def exact_messages_routes():\n"
        "    return {}\n",
        encoding="utf-8",
    )
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/messages*\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: legacy_deleted\n"
        "    replacement_status: deleted\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/messages*\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_exact\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n",
        encoding="utf-8",
    )

    assert check_messages_broad_wildcard_deletion(tmp_path) == []


def test_sidebar_readonly_closeout_guard_flags_legacy_fallback_and_bad_lifecycle(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    customer_api = tmp_path / "aicrm_next/customer_read_model/api.py"
    identity_api = tmp_path / "aicrm_next/identity_contact/api.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    customer_api.parent.mkdir(parents=True)
    identity_api.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text(
        '@router.api_route("/api/sidebar/profile", methods=["GET"])\n'
        '@router.api_route("/api/sidebar/bind-mobile", methods=["POST"])\n'
        "def legacy_profile():\n"
        "    return {}\n",
        encoding="utf-8",
    )
    customer_api.write_text(
        '@router.get("/api/sidebar/profile")\n'
        "def sidebar_profile():\n"
        "    from aicrm_next.integration_gateway import legacy_sidebar_read_facade\n"
        "    return {\"fallback_used\": True}\n",
        encoding="utf-8",
    )
    identity_api.write_text("", encoding="utf-8")
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/sidebar/profile\n"
        "    runtime_owner: production_compat\n"
        "    legacy_fallback_allowed: true\n"
        "    delete_status: active\n"
        "    replacement_status: validating\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/sidebar/profile\n"
        "    current_runtime_owner: production_compat\n"
        "    production_behavior: legacy_forward\n"
        "    legacy_fallback_allowed: true\n"
        "  - route_pattern: /api/sidebar/bind-mobile\n"
        "    production_behavior: readonly_facade\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n",
        encoding="utf-8",
    )

    violations = check_sidebar_readonly_closeout_lock(tmp_path)
    codes = {violation.code for violation in violations}

    assert "sidebar_readonly_production_compat_route" in codes
    assert "sidebar_readonly_legacy_facade" in codes
    assert "sidebar_readonly_fallback_used_true" in codes
    assert "sidebar_readonly_registry_legacy_allowed" in codes
    assert "sidebar_readonly_registry_delete_status" in codes
    assert "sidebar_readonly_manifest_legacy_forward" in codes
    assert "sidebar_write_production_compat_route" in codes
    assert "sidebar_write_manifest_behavior" in codes


def test_sidebar_readonly_closeout_guard_allows_locked_readonly_and_out_of_scope_write_routes(tmp_path: Path) -> None:
    compat = tmp_path / "aicrm_next/production_compat/api.py"
    customer_api = tmp_path / "aicrm_next/customer_read_model/api.py"
    identity_api = tmp_path / "aicrm_next/identity_contact/api.py"
    registry = tmp_path / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest = tmp_path / "docs/route_ownership/production_route_ownership_manifest.yaml"
    compat.parent.mkdir(parents=True)
    customer_api.parent.mkdir(parents=True)
    identity_api.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)

    compat.write_text('@router.api_route("/api/sidebar/jssdk-config", methods=["GET"])\ndef jssdk_route():\n    return {}\n', encoding="utf-8")
    customer_api.write_text(
        '@router.get("/api/sidebar/profile")\n'
        "def sidebar_profile():\n"
        "    return {\"route_owner\": \"ai_crm_next\", \"fallback_used\": False}\n",
        encoding="utf-8",
    )
    identity_api.write_text(
        '@router.get("/api/sidebar/binding-status")\n'
        "def sidebar_binding_status():\n"
        "    return {\"route_owner\": \"ai_crm_next\", \"fallback_used\": False}\n",
        encoding="utf-8",
    )
    registry.write_text(
        "routes:\n"
        "  - path_pattern: /api/sidebar/profile\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - path_pattern: /api/sidebar/binding-status\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "  - path_pattern: /api/sidebar/bind-mobile\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    adapter_mode: real_blocked\n"
        "  - path_pattern: /api/sidebar/signup-tags/mark\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    adapter_mode: real_blocked\n"
        "  - path_pattern: /api/sidebar/lead-pool/upsert-class-term\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    adapter_mode: real_blocked\n"
        "  - path_pattern: /api/sidebar/marketing-status/set-followup-segment\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    adapter_mode: real_blocked\n"
        "  - path_pattern: /api/sidebar/marketing-status/mark-enrolled\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    adapter_mode: real_blocked\n"
        "  - path_pattern: /api/sidebar/marketing-status/unmark-enrolled\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    adapter_mode: real_blocked\n"
        "  - path_pattern: /api/sidebar/v2/profile\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    adapter_mode: real_blocked\n"
        "  - path_pattern: /api/sidebar/v2/materials/send\n"
        "    runtime_owner: next_native\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_status: deletion_locked\n"
        "    replacement_status: locked\n"
        "    adapter_mode: real_blocked\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "routes:\n"
        "  - route_pattern: /api/sidebar/profile\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: readonly_facade\n"
        "    legacy_fallback_allowed: false\n"
        "  - route_pattern: /api/sidebar/binding-status\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: readonly_facade\n"
        "    legacy_fallback_allowed: false\n"
        "  - route_pattern: /api/sidebar/bind-mobile\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n"
        "  - route_pattern: /api/sidebar/signup-tags/mark\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n"
        "  - route_pattern: /api/sidebar/lead-pool/upsert-class-term\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n"
        "  - route_pattern: /api/sidebar/marketing-status/set-followup-segment\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n"
        "  - route_pattern: /api/sidebar/marketing-status/mark-enrolled\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n"
        "  - route_pattern: /api/sidebar/marketing-status/unmark-enrolled\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n"
        "  - route_pattern: /api/sidebar/v2/profile\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n"
        "  - route_pattern: /api/sidebar/v2/materials/send\n"
        "    current_runtime_owner: next\n"
        "    production_behavior: next_command\n"
        "    legacy_fallback_allowed: false\n"
        "    delete_ready: true\n"
        "  - route_pattern: /api/sidebar/jssdk-config\n"
        "    production_behavior: legacy_forward\n"
        "    legacy_fallback_allowed: true\n"
        "    delete_ready: false\n",
        encoding="utf-8",
    )

    violations = check_sidebar_readonly_closeout_lock(tmp_path)
    codes = {violation.code for violation in violations}

    assert "sidebar_readonly_production_compat_route" not in codes
    assert "sidebar_readonly_legacy_facade" not in codes
    assert "sidebar_write_production_compat_route" not in codes
    assert "sidebar_write_manifest_legacy_allowed" not in codes
