from __future__ import annotations

import json
import re
from pathlib import Path

from aicrm_next.commerce.parity_spec import DEFAULT_SAFE_ENDPOINTS as COMMERCE_DEFAULT_SAFE_ENDPOINTS
from aicrm_next.commerce.parity_spec import ENDPOINT_SPECS as COMMERCE_SPECS
from aicrm_next.commerce.parity_spec import WRITE_ENDPOINTS as COMMERCE_WRITE_ENDPOINTS
from aicrm_next.commerce.parity_spec import compare_endpoint_payloads as compare_commerce_payloads
from aicrm_next.commerce.parity_spec import validate_payload as validate_commerce_payload
from aicrm_next.media_library.parity_spec import ENDPOINT_SPECS as MEDIA_SPECS
from aicrm_next.media_library.parity_spec import compare_endpoint_payloads as compare_media_payloads
from aicrm_next.media_library.parity_spec import validate_payload as validate_media_payload
from conftest import make_client
from tools import compare_commerce_parity as commerce_compare_tool
from tools.compare_commerce_parity import run_compare as run_commerce_compare
from tools.compare_media_library_parity import run_compare as run_media_compare

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMERCE_FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "old_commerce"
MEDIA_FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "old_media_library"


def _fixture_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["payload"]


def test_commerce_and_media_specs_cover_required_surfaces() -> None:
    assert {"products.default", "product_detail.default", "checkout_wechat.default", "checkout_alipay.default", "wechat_transactions.default", "alipay_transactions.default"} <= set(COMMERCE_SPECS)
    assert {"image_library.default", "attachment_library.default", "miniprogram_library.default"} <= set(MEDIA_SPECS)


def test_commerce_default_safe_endpoints_exclude_checkout_writes() -> None:
    assert "checkout_wechat.default" not in COMMERCE_DEFAULT_SAFE_ENDPOINTS
    assert "checkout_alipay.default" not in COMMERCE_DEFAULT_SAFE_ENDPOINTS
    assert {"checkout_wechat.default", "checkout_alipay.default"} == set(COMMERCE_WRITE_ENDPOINTS)
    assert set(COMMERCE_DEFAULT_SAFE_ENDPOINTS) == {"products.default", "product_detail.default", "wechat_transactions.default", "alipay_transactions.default"}


def test_old_commerce_and_media_fixtures_conform_and_are_masked() -> None:
    phone_like = re.compile(r"1[3-9]\d{9}")
    for fixture_dir, validator in [(COMMERCE_FIXTURE_DIR, validate_commerce_payload), (MEDIA_FIXTURE_DIR, validate_media_payload)]:
        for path in fixture_dir.glob("*.json"):
            text = path.read_text(encoding="utf-8")
            assert not phone_like.search(text)
            assert "openid_masked" in text or "openid" not in text
            assert "appid_masked" in text or "appid" not in text
            assert "external_user_masked" in text or "external_userid" not in text
            assert "transaction_masked" in text or "transaction_id" not in text
            assert not validator(path.stem, json.loads(text)["payload"])


def test_next_commerce_and_media_endpoints_conform_to_parity_specs() -> None:
    client = make_client()
    for endpoint_name, spec in COMMERCE_SPECS.items():
        response = client.request(spec.method, spec.path, json=spec.body if spec.method == "POST" else None)
        assert response.status_code == spec.expected_status
        assert not validate_commerce_payload(endpoint_name, response.json())
    for endpoint_name, spec in MEDIA_SPECS.items():
        response = client.request(spec.method, spec.path, json=spec.body if spec.method == "POST" else None)
        assert response.status_code == spec.expected_status
        assert not validate_media_payload(endpoint_name, response.json())


def test_next_commerce_fake_checkout_still_conforms_to_parity_specs() -> None:
    client = make_client()
    for endpoint_name in COMMERCE_WRITE_ENDPOINTS:
        spec = COMMERCE_SPECS[endpoint_name]
        response = client.request(spec.method, spec.path, json=spec.body)
        assert response.status_code == spec.expected_status
        payload = response.json()
        assert payload["fake_payment"] is True
        assert payload["payment_status"] == "pending"
        assert not validate_commerce_payload(endpoint_name, payload)


def test_compare_tools_detect_missing_required_key() -> None:
    commerce_payload = _fixture_payload(COMMERCE_FIXTURE_DIR / "products.default.json")
    assert any(issue["rule"] == "required_key" for issue in compare_commerce_payloads("products.default", commerce_payload, {k: v for k, v in commerce_payload.items() if k != "items"}))
    media_payload = _fixture_payload(MEDIA_FIXTURE_DIR / "image_library.default.json")
    assert any(issue["rule"] == "required_key" for issue in compare_media_payloads("image_library.default", media_payload, {k: v for k, v in media_payload.items() if k != "items"}))


def test_commerce_and_media_compare_tools_fixture_mode(tmp_path: Path) -> None:
    commerce_args = type(
        "Args",
        (),
        {
            "old_fixture_dir": str(COMMERCE_FIXTURE_DIR),
            "old_base_url": "",
            "next_base_url": "",
            "next_testclient": True,
            "output_md": str(tmp_path / "commerce.md"),
            "output_json": str(tmp_path / "commerce.json"),
        },
    )()
    media_args = type(
        "Args",
        (),
        {
            "old_fixture_dir": str(MEDIA_FIXTURE_DIR),
            "old_base_url": "",
            "next_base_url": "",
            "next_testclient": True,
            "output_md": str(tmp_path / "media.md"),
            "output_json": str(tmp_path / "media.json"),
        },
    )()
    assert run_commerce_compare(commerce_args)["ok"] is True
    assert run_media_compare(media_args)["ok"] is True


def test_commerce_compare_fixture_mode_includes_checkout_writes(tmp_path: Path) -> None:
    args = type(
        "Args",
        (),
        {
            "old_fixture_dir": str(COMMERCE_FIXTURE_DIR),
            "old_base_url": "",
            "next_base_url": "",
            "next_testclient": True,
            "allow_old_write_endpoints": False,
            "output_md": str(tmp_path / "commerce.md"),
            "output_json": str(tmp_path / "commerce.json"),
        },
    )()
    report = run_commerce_compare(args)
    result_by_endpoint = {item["endpoint"]: item for item in report["results"]}
    assert result_by_endpoint["checkout_wechat.default"]["status"] == "PASS"
    assert result_by_endpoint["checkout_alipay.default"]["status"] == "PASS"


def test_commerce_compare_old_base_url_skips_checkout_writes(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str, str]] = []

    def fake_fetch_http(base_url: str, endpoint_name: str) -> dict:
        spec = COMMERCE_SPECS[endpoint_name]
        calls.append((base_url, endpoint_name, spec.method))
        assert endpoint_name not in COMMERCE_WRITE_ENDPOINTS
        return json.loads((COMMERCE_FIXTURE_DIR / f"{endpoint_name}.json").read_text(encoding="utf-8"))

    monkeypatch.setattr(commerce_compare_tool, "_fetch_http", fake_fetch_http)
    args = type(
        "Args",
        (),
        {
            "old_fixture_dir": "",
            "old_base_url": "http://old.example.test",
            "next_base_url": "",
            "next_testclient": True,
            "allow_old_write_endpoints": False,
            "output_md": str(tmp_path / "commerce.md"),
            "output_json": str(tmp_path / "commerce.json"),
        },
    )()
    report = run_commerce_compare(args)
    assert report["ok"] is True
    assert all(method == "GET" for _, _, method in calls)
    assert not any(endpoint in COMMERCE_WRITE_ENDPOINTS for _, endpoint, _ in calls)
    result_by_endpoint = {item["endpoint"]: item for item in report["results"]}
    for endpoint_name in COMMERCE_WRITE_ENDPOINTS:
        assert result_by_endpoint[endpoint_name]["status"] == "SKIPPED"
        assert result_by_endpoint[endpoint_name]["reason"] == "old_write_endpoint_disabled"
        assert result_by_endpoint[endpoint_name]["issues"][0]["severity"] == "skip"


def test_commerce_compare_old_write_flag_defaults_false_and_warns() -> None:
    parser = commerce_compare_tool.build_parser()
    args = parser.parse_args(
        [
            "--old-base-url",
            "http://old.example.test",
            "--next-testclient",
            "--output-md",
            "/tmp/commerce.md",
            "--output-json",
            "/tmp/commerce.json",
        ]
    )
    assert args.allow_old_write_endpoints is False
    assert "DANGEROUS" in parser.format_help()
