from __future__ import annotations

import json
import re
from pathlib import Path

from conftest import make_client

from aicrm_next.questionnaire.parity_spec import ENDPOINT_SPECS, compare_endpoint_payloads, validate_payload
from tools.compare_questionnaire_parity import run_compare

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "old_questionnaire"


def _fixture_payload(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))["payload"]


def test_questionnaire_parity_spec_covers_required_surfaces() -> None:
    assert {
        "admin_list.default",
        "admin_detail.default",
        "admin_preflight.default",
        "public_get.default",
        "submit.default",
    } <= set(ENDPOINT_SPECS)


def test_old_questionnaire_fixtures_conform_and_are_masked() -> None:
    phone_like = re.compile(r"1[3-9]\d{9}")
    for path in FIXTURE_DIR.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert not phone_like.search(text)
        assert "openid_masked" in text or "openid" not in text
        assert "unionid_masked" in text or "unionid" not in text
        assert "external_user_masked" in text or "external_userid" not in text
        endpoint_name = path.stem
        assert not validate_payload(endpoint_name, json.loads(text)["payload"])


def test_next_questionnaire_endpoints_conform_to_parity_spec() -> None:
    client = make_client()
    for endpoint_name, spec in ENDPOINT_SPECS.items():
        response = client.request(spec.method, spec.path, json=spec.body if spec.method == "POST" else None)
        assert response.status_code == spec.expected_status
        assert not validate_payload(endpoint_name, response.json())


def test_questionnaire_compare_detects_missing_required_key() -> None:
    old_payload = _fixture_payload("admin_list.default")
    next_payload = {key: value for key, value in old_payload.items() if key != "items"}
    issues = compare_endpoint_payloads("admin_list.default", old_payload, next_payload)
    assert any(issue["rule"] == "required_key" and issue.get("key") == "items" for issue in issues)


def test_questionnaire_compare_tool_fixture_mode(tmp_path: Path) -> None:
    args = type(
        "Args",
        (),
        {
            "old_fixture_dir": str(FIXTURE_DIR),
            "old_base_url": "",
            "next_base_url": "",
            "next_testclient": True,
            "output_md": str(tmp_path / "questionnaire.md"),
            "output_json": str(tmp_path / "questionnaire.json"),
        },
    )()
    report = run_compare(args)
    assert report["ok"] is True
