from __future__ import annotations

import json
from pathlib import Path

from tools import generate_gray_release_report

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_doc(name: str) -> str:
    return (PROJECT_ROOT / "docs" / name).read_text(encoding="utf-8")


def _included_section(text: str, heading: str) -> str:
    start = text.index(heading)
    next_heading = text.find("\n## Batch", start + len(heading))
    section = text[start:] if next_heading == -1 else text[start:next_heading]
    included_start = section.index("Included routes:")
    excluded_start = section.index("Excluded routes:")
    return section[included_start:excluded_start]


def test_route_level_gray_release_batches_include_batch_0_to_5_and_retire_automation() -> None:
    text = _read_doc("route_level_gray_release_batches.md")
    for number in range(6):
        assert f"## Batch {number}" in text
    assert "## Retired Automation Conversion Readonly Batch" in text
    assert "tools/automation_readonly_gray_smoke.py" not in text


def test_no_batch_included_routes_contain_known_write_routes() -> None:
    text = _read_doc("route_level_gray_release_batches.md")
    forbidden = [
        "POST ",
        "PUT ",
        "DELETE ",
        "checkout",
        "notify",
        "do-not-disturb",
        "batch-send",
        "/submit",
        "oauth/callback",
        "activation-webhook",
        "push-openclaw",
        "workflow runtime",
    ]
    for number in range(1, 6):
        included = _included_section(text, f"## Batch {number}")
        lowered = included.lower()
        for fragment in forbidden:
            assert fragment.lower() not in lowered


def test_product_batch_excludes_checkout_and_notify() -> None:
    text = _read_doc("route_level_gray_release_batches.md")
    section = text[text.index("## Batch 2") : text.index("## Batch 3")]
    assert "checkout" in section
    assert "payment notify" in section
    assert "POST /api/checkout/wechat" in section


def test_user_ops_batch_excludes_dnd_and_batch_send() -> None:
    text = _read_doc("route_level_gray_release_batches.md")
    section = text[text.index("## Batch 4") : text.index("## Batch 5")]
    assert "DND" in section
    assert "batch-send preview" in section
    assert "batch-send execute" in section


def test_questionnaire_batch_excludes_submit_and_oauth_callback() -> None:
    text = _read_doc("route_level_gray_release_batches.md")
    section = text[text.index("## Batch 5") : text.index("## Retired Automation Conversion Readonly Batch")]
    assert "submit" in section
    assert "OAuth callback" in section


def test_automation_batch_is_retired_from_readonly_canary_scope() -> None:
    text = _read_doc("route_level_gray_release_batches.md")
    section = text[text.index("## Retired Automation Conversion Readonly Batch") :]
    assert "ai_audience_ops" in section
    assert "404/410" in section
    assert "Runtime V2" in section


def test_proxy_template_is_pseudo_and_has_no_production_secrets() -> None:
    text = _read_doc("route_level_proxy_template.md")
    assert text.count("PSEUDO ONLY") >= 6
    forbidden = ["prod.example", "https://prod", "http://prod", "secret=", "password=", "api_key=", "token="]
    lowered = text.lower()
    for fragment in forbidden:
        assert fragment not in lowered


def test_signoff_template_includes_rollback_owner_and_go_no_go() -> None:
    text = _read_doc("gray_release_signoff_template.md")
    assert "rollback owner" in text
    assert "go/no-go decision" in text
    assert "external adapters mode" in text


def test_report_generator_aggregates_blockers(tmp_path: Path) -> None:
    smoke = tmp_path / "smoke.json"
    parity = tmp_path / "parity.json"
    smoke.write_text(
        json.dumps(
            {
                "ok": False,
                "blockers": [{"reason": "route_returned_5xx"}],
                "warnings": [{"reason": "legacy_drift"}],
                "skipped": [{"reason": "no_sample"}],
                "side_effect_safety": {"old_write_endpoints_executed": False},
            }
        ),
        encoding="utf-8",
    )
    parity.write_text(json.dumps({"overall": "PASS", "blockers": []}), encoding="utf-8")
    report = generate_gray_release_report.build_report("media_readonly", str(smoke), str(parity))
    assert report["go_no_go_recommendation"] == "NO_GO"
    assert report["blockers"] == [{"reason": "route_returned_5xx"}]
    assert report["warnings"] == [{"reason": "legacy_drift"}]
    assert report["skipped"] == [{"reason": "no_sample"}]
    assert report["side_effect_safety"]["old_write_endpoints_executed"] is False


def test_report_generator_refuses_missing_required_input_json(tmp_path: Path) -> None:
    parity = tmp_path / "parity.json"
    parity.write_text(json.dumps({"overall": "PASS"}), encoding="utf-8")
    missing = tmp_path / "missing.json"
    try:
        generate_gray_release_report.build_report("media_readonly", str(missing), str(parity))
    except FileNotFoundError as exc:
        assert "smoke JSON does not exist" in str(exc)
    else:
        raise AssertionError("expected missing smoke json to raise")


def test_gray_release_tool_does_not_import_old_backend() -> None:
    text = (PROJECT_ROOT / "tools" / "generate_gray_release_report.py").read_text(encoding="utf-8")
    assert "import wecom_ability_service" not in text
    assert "from wecom_ability_service" not in text
    assert "import openclaw_service" not in text
    assert "from openclaw_service" not in text
