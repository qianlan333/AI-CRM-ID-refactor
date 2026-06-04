from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPAT_ROUTER = "production_compat" + "_router"
COMPAT_WILDCARD_ROUTER = "production_compat" + "_wildcard_router"


def test_production_compat_module_is_empty_historical_shell() -> None:
    source = (ROOT / "aicrm_next/production_compat/api.py").read_text(encoding="utf-8")

    assert "@router.api_route" not in source
    assert "@wildcard_router.api_route" not in source
    assert "forward_to_legacy_flask" not in source
    assert "legacy_flask_facade" not in source
    assert "router = APIRouter()" in source
    assert "wildcard_router = APIRouter()" in source


def test_app_startup_no_longer_imports_or_includes_production_compat() -> None:
    source = (ROOT / "aicrm_next/main.py").read_text(encoding="utf-8")

    assert COMPAT_ROUTER not in source
    assert COMPAT_WILDCARD_ROUTER not in source
    assert "aicrm_next.production_compat.api" not in source


def test_api_docs_router_sources_do_not_include_production_compat() -> None:
    source = (ROOT / "aicrm_next/frontend_compat/api_docs_view_model.py").read_text(encoding="utf-8")

    assert COMPAT_ROUTER not in source
    assert COMPAT_WILDCARD_ROUTER not in source

