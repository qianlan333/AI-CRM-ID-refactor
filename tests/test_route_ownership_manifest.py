from __future__ import annotations

import yaml
from fastapi import FastAPI

from aicrm_next.main import app
from aicrm_next.shared.route_ownership import collect_route_inventory, validate_route_manifest


def _write_manifest(path, routes):
    path.write_text(yaml.safe_dump({"routes": routes}, sort_keys=False), encoding="utf-8")


def test_route_ownership_manifest_covers_current_app_routes() -> None:
    errors = validate_route_manifest(app, "docs/architecture/route_ownership_manifest.yml")
    assert errors == []


def test_route_ownership_manifest_matches_non_static_route_count() -> None:
    inventory = collect_route_inventory(app)
    with open("docs/architecture/route_ownership_manifest.yml", encoding="utf-8") as handle:
        manifest = yaml.safe_load(handle)

    assert len(manifest["routes"]) == len(inventory)
    assert len(manifest["routes"]) >= 600


def test_route_ownership_manifest_rejects_unknown_owner(tmp_path) -> None:
    test_app = FastAPI()

    @test_app.get("/demo", name="demo_route")
    def demo_route():
        return {"ok": True}

    _write_manifest(
        tmp_path / "routes.yml",
        [
            {
                "path": "/demo",
                "methods": ["GET"],
                "route_name": "demo_route",
                "capability_owner": "unknown",
                "runtime_owner": "ai_crm_next",
                "layer": "api",
                "external_effects": "none",
                "data_source": "read_model",
                "requires_auth": False,
                "rollback": "previous_release",
            }
        ],
    )

    errors = validate_route_manifest(test_app, tmp_path / "routes.yml")

    assert any("unknown_owner" in error for error in errors)
    assert any("capability_owner" in error for error in errors)


def test_route_ownership_manifest_reports_missing_route(tmp_path) -> None:
    test_app = FastAPI()

    @test_app.post("/demo", name="demo_route")
    def demo_route():
        return {"ok": True}

    _write_manifest(tmp_path / "routes.yml", [])

    errors = validate_route_manifest(test_app, tmp_path / "routes.yml")

    assert any("missing_route_owner" in error for error in errors)
    assert any("/demo" in error for error in errors)
