from __future__ import annotations

import json

import tools.check_post_820_batch_exact_route_cleanup as checker


def test_batch_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_selected_exact_decorators_absent_and_wildcards_retained() -> None:
    text = checker.PRODUCTION_COMPAT.read_text(encoding="utf-8")
    for route in checker.SELECTED_EXACT_ROUTES:
        assert f'@router.api_route("{route}", methods=_ALL_METHODS)' not in text
    for route in checker.RETAINED_WILDCARD_ROUTES:
        assert f'@router.api_route("{route}", methods=_ALL_METHODS)' in text
    assert "wildcard_router = APIRouter()" in text


def test_next_native_exact_routes_exist() -> None:
    text = checker.NATIVE_API.read_text(encoding="utf-8")
    for route, patterns in checker.NEXT_NATIVE_EXACT_PATTERNS.items():
        assert any(checker.re.search(pattern, text) for pattern in patterns), route


def test_unrelated_production_compat_routes_remain() -> None:
    text = checker.PRODUCTION_COMPAT.read_text(encoding="utf-8")
    for route in checker.UNRELATED_PRODUCTION_COMPAT_ROUTES:
        assert checker._contains_route(text, route), route


def test_cleanup_result_keeps_runtime_wildcard_and_delete_ready_blocked() -> None:
    data = checker.load_yaml(checker.PLAN_YAML)
    result = data["cleanup_result"]
    assert result["production_compat_cleanups_executed"] == list(checker.SELECTED_EXACT_ROUTES)
    assert result["runtime_deletions_executed"] == []
    assert result["wildcard_cleanup_executed"] is False
    assert result["delete_ready"] is False
    assert data["authorizations"]["delete_ready"] is False
    assert data["authorizations"]["runtime_deletion_authorized"] is False
