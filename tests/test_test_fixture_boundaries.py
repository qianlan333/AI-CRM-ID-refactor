from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFTEST = ROOT / "tests" / "conftest.py"


def _fixture_block(source: str, fixture_name: str) -> str:
    marker = f"def {fixture_name}("
    start = source.find(marker)
    assert start >= 0, f"missing fixture {fixture_name}"
    next_start = len(source)
    for candidate in ("\n@pytest.fixture", "\ndef "):
        pos = source.find(candidate, start + len(marker))
        if pos >= 0:
            next_start = min(next_start, pos + 1)
    return source[start:next_start]


def test_next_and_legacy_test_fixtures_exist() -> None:
    source = CONFTEST.read_text(encoding="utf-8")

    for fixture_name in ("next_app", "next_client", "legacy_app", "legacy_client", "legacy_app_context"):
        assert f"def {fixture_name}(" in source
    assert "def build_legacy_pg_test_app(" in source


def test_default_app_and_client_do_not_construct_legacy_flask_app() -> None:
    source = CONFTEST.read_text(encoding="utf-8")

    assert "wecom_ability_service" not in _fixture_block(source, "app")
    assert "test_client(" not in _fixture_block(source, "client")
    assert "legacy_app" not in _fixture_block(source, "client")
    assert "legacy_client" not in _fixture_block(source, "client")


def test_next_fixtures_do_not_import_legacy_package() -> None:
    source = CONFTEST.read_text(encoding="utf-8")

    assert "wecom_ability_service" not in _fixture_block(source, "next_app")
    assert "wecom_ability_service" not in _fixture_block(source, "next_client")


def test_build_pg_test_app_is_deprecated_alias() -> None:
    source = CONFTEST.read_text(encoding="utf-8")
    block = _fixture_block(source, "build_pg_test_app")

    assert "Deprecated alias" in block
    assert "build_legacy_pg_test_app" in block
