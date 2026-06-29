from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from tools import run_gray_rehearsal_batch as rehearsal


def _args(tmp_path: Path, *, batch: str = "media_readonly") -> Namespace:
    return Namespace(
        batch=batch,
        next_testclient=True,
        next_base_url="",
        old_base_url="",
        output_md=str(tmp_path / "report.md"),
        output_json=str(tmp_path / "report.json"),
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_supports_media_readonly_batch() -> None:
    assert "media_readonly" in rehearsal.BATCHES


def test_rejects_unknown_batch(tmp_path: Path) -> None:
    report = rehearsal.run_rehearsal(_args(tmp_path, batch="unknown"))
    assert report["ok"] is False
    assert report["blockers"][0]["reason"] == "unsupported_batch"


def test_media_readonly_batch_includes_only_get_routes() -> None:
    batch = rehearsal.BATCHES["media_readonly"]
    assert batch.included_routes
    assert all(route.startswith("GET ") for route in batch.included_routes)


def test_media_readonly_batch_excludes_write_routes() -> None:
    batch = rehearsal.BATCHES["media_readonly"]
    assert any(route.startswith("POST ") for route in batch.excluded_routes)
    assert any(route.startswith("PUT ") for route in batch.excluded_routes)
    assert any(route.startswith("DELETE ") for route in batch.excluded_routes)
    assert not any(route.startswith(("POST ", "PUT ", "DELETE ")) for route in batch.included_routes)


def test_side_effect_safety_all_false() -> None:
    report = rehearsal._side_effect_safety(
        {
            "side_effect_safety": {
                "old_write_endpoints_executed": False,
                "external_upload_executed": False,
                "wecom_media_upload_executed": False,
                "default_endpoints_get_only": True,
            }
        }
    )
    assert report["production_config_modified"] is False
    assert report["old_write_endpoints_executed"] is False
    assert report["cloud_storage_upload_executed"] is False
    assert report["wecom_media_upload_executed"] is False
    assert report["real_traffic_cutover_executed"] is False


def test_rollback_dry_run_present() -> None:
    rollback = rehearsal._rollback_dry_run(rehearsal.BATCHES["media_readonly"])
    assert rollback["route_flag_rollback_instruction"] == "AICRM_NEXT_ROUTE_MEDIA_READONLY=false"
    assert rollback["expected_owner_after_rollback"] == "old Flask"
    assert rollback["rollback_verified"] == "dry-run only"


def test_report_includes_route_flags_and_signoff_reference(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command: list[str], *, cwd: Path):
        output_json = Path(command[command.index("--output-json") + 1])
        if "media_library_gray_smoke.py" in command[1]:
            _write_json(
                output_json,
                {
                    "ok": True,
                    "route_results": [{"name": "image_page", "method": "GET", "path": "/admin/image-library", "ok": True}],
                    "blockers": [],
                    "warnings": [],
                    "skipped": [],
                    "side_effect_safety": {
                        "old_write_endpoints_executed": False,
                        "external_upload_executed": False,
                        "wecom_media_upload_executed": False,
                        "default_endpoints_get_only": True,
                    },
                },
            )
        else:
            _write_json(output_json, {"overall": "PASS", "blockers": [], "warnings": [], "skipped": []})
        return {"ok": True, "returncode": 0, "stdout": "", "stderr": "", "command": command}

    monkeypatch.setattr(rehearsal, "_run_command", fake_run)
    monkeypatch.setattr(rehearsal, "_screenshot_baseline_result", lambda _path: {"ok": True, "summary": {"routes": 14}})
    report = rehearsal.run_rehearsal(_args(tmp_path))
    assert report["ok"] is True
    assert report["route_flags"]["AICRM_NEXT_ROUTE_MEDIA_READONLY"] is True
    assert report["route_flags"]["AICRM_NEXT_ROUTE_MEDIA_WRITES"] is False
    assert report["signoff_reference"] == "docs/archive/experiments_ai_crm_next/docs/gray_release_signoff_template.md"


def test_no_production_config_modified() -> None:
    safety = rehearsal._side_effect_safety({"side_effect_safety": {}})
    rollback = rehearsal._rollback_dry_run(rehearsal.BATCHES["media_readonly"])
    assert safety["production_config_modified"] is False
    assert rollback["production_config_modified"] is False


def test_old_base_url_refuses_non_get_endpoint(monkeypatch) -> None:
    batch = rehearsal.BatchDefinition(
        name="bad",
        included_routes=("POST /api/admin/image-library",),
        excluded_routes=(),
        route_flags={},
    )
    monkeypatch.setitem(rehearsal.BATCHES, "bad", batch)
    blockers = rehearsal._validate_batch(batch)
    assert blockers and blockers[0]["reason"] == "write_route_included"


def test_report_generator_integration_works(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command: list[str], *, cwd: Path):
        output_json = Path(command[command.index("--output-json") + 1])
        if "media_library_gray_smoke.py" in command[1]:
            _write_json(
                output_json,
                {
                    "ok": True,
                    "route_results": [],
                    "blockers": [],
                    "warnings": [],
                    "skipped": [],
                    "side_effect_safety": {"old_write_endpoints_executed": False},
                },
            )
        else:
            _write_json(output_json, {"overall": "PASS", "blockers": []})
        return {"ok": True, "returncode": 0, "stdout": "", "stderr": "", "command": command}

    monkeypatch.setattr(rehearsal, "_run_command", fake_run)
    monkeypatch.setattr(rehearsal, "_screenshot_baseline_result", lambda _path: {"ok": True})
    report = rehearsal.run_rehearsal(_args(tmp_path))
    assert report["gray_release_report"]["recommendation"] == "GO"
    assert Path(report["gray_release_report"]["json"]).exists()


def test_no_old_backend_imports() -> None:
    text = (rehearsal.PROJECT_ROOT / "tools" / "run_gray_rehearsal_batch.py").read_text(encoding="utf-8")
    assert "import wecom_ability_service" not in text
    assert "from wecom_ability_service" not in text
    assert "import openclaw_service" not in text
    assert "from openclaw_service" not in text
