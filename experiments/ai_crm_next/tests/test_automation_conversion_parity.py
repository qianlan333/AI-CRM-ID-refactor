from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

from conftest import make_client

from aicrm_next.automation_engine.parity_spec import DEFAULT_SAFE_ENDPOINTS, ENDPOINT_SPECS, compare_endpoint_payloads, validate_payload

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "old_automation_conversion"


def _load_fixture(name: str) -> dict:
    data = json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return data["payload"]


def test_automation_parity_spec_covers_required_areas() -> None:
    assert {
        "overview.default",
        "pools.default",
        "members.default",
        "member_detail.default",
        "activation_webhook.default",
        "execution_records.default",
    } <= set(DEFAULT_SAFE_ENDPOINTS)


def test_old_automation_fixtures_conform_to_parity_spec_and_are_masked() -> None:
    fixture_text = "\n".join(path.read_text(encoding="utf-8") for path in FIXTURE_DIR.glob("*.json"))
    assert "138" not in fixture_text
    assert "wx_ext_" not in fixture_text
    assert "mobile_masked_001" in fixture_text
    for endpoint_name in DEFAULT_SAFE_ENDPOINTS:
        assert validate_payload(endpoint_name, _load_fixture(endpoint_name)) == []


def test_next_automation_endpoints_conform_to_parity_spec() -> None:
    client = make_client()
    for endpoint_name in DEFAULT_SAFE_ENDPOINTS:
        spec = ENDPOINT_SPECS[endpoint_name]
        response = client.request(spec.method, spec.path, json=spec.body if spec.method == "POST" else None)
        assert response.status_code == spec.expected_status
        assert validate_payload(endpoint_name, response.json()) == []


def test_automation_compare_detects_missing_required_key() -> None:
    old_payload = _load_fixture("members.default")
    next_payload = copy.deepcopy(old_payload)
    del next_payload["items"][0]["member_id"]
    issues = compare_endpoint_payloads("members.default", old_payload, next_payload)
    assert any(issue["rule"] == "required_key" and issue.get("key") == "member_id" for issue in issues)


def test_automation_compare_tool_fixture_mode(tmp_path: Path) -> None:
    output_md = tmp_path / "automation_parity.md"
    output_json = tmp_path / "automation_parity.json"
    result = subprocess.run(
        [
            sys.executable,
            "tools/compare_automation_conversion_parity.py",
            "--old-fixture-dir",
            "tests/fixtures/old_automation_conversion",
            "--next-testclient",
            "--output-md",
            str(output_md),
            "--output-json",
            str(output_json),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(output_json.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert "Automation Conversion Parity Report" in output_md.read_text(encoding="utf-8")
