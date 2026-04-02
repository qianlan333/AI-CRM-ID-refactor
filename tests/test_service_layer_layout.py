from __future__ import annotations

from pathlib import Path

from wecom_ability_service.domains import DOMAIN_LAYOUTS


def test_domain_layout_registry_matches_domain_directories():
    domains_dir = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "domains"
    actual = {
        path.name
        for path in domains_dir.iterdir()
        if path.is_dir() and not path.name.startswith("__")
    }
    assert set(DOMAIN_LAYOUTS.keys()) == actual


def test_domain_layout_files_match_declared_mode():
    domains_dir = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "domains"
    for domain_name, spec in DOMAIN_LAYOUTS.items():
        domain_dir = domains_dir / domain_name
        assert (domain_dir / "service.py").exists(), f"{domain_name} must expose service.py"
        if spec.mode == "simple":
            assert (domain_dir / "repo.py").exists(), f"{domain_name} simple mode must expose repo.py"
        elif spec.mode == "complex":
            assert (domain_dir / "queries.py").exists(), f"{domain_name} complex mode must expose queries.py"
            assert (domain_dir / "writers.py").exists(), f"{domain_name} complex mode must expose writers.py"
        else:
            raise AssertionError(f"unknown mode: {spec.mode}")


def test_services_py_remains_a_thin_facade():
    services_path = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "services.py"
    source = services_path.read_text(encoding="utf-8")
    assert "Thin compatibility facade" in source
    assert "do not place new domain implementation here" in source
    forbidden_fragments = [
        "get_db(",
        ".execute(",
        "requests.",
        "import requests",
        "WeComClient.from_app(",
        "WeComClient.from_contact_app(",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in source, f"services.py must not contain {fragment}"


def test_service_layer_layout_doc_exists():
    doc_path = Path(__file__).resolve().parents[1] / "docs" / "architecture" / "service_layer_layout.md"
    assert doc_path.exists()
    source = doc_path.read_text(encoding="utf-8")
    assert "Only two domain layout modes are allowed" in source
    assert "`wecom_ability_service/services.py` stays as a thin compatibility facade" in source
