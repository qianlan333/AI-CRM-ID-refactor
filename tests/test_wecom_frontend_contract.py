from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


ROOT = Path(__file__).resolve().parents[1]
CHANNEL_TEMPLATE = ROOT / "aicrm_next" / "automation_engine" / "templates" / "admin_console" / "channel_code_center.html"
WECOM_STATUS = ROOT / "frontend" / "admin" / "wecom" / "wecom_status.ts"
WECOM_OVERVIEW = ROOT / "frontend" / "admin" / "wecom" / "wecom_overview.ts"


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.setenv("SECRET_KEY", "p1-wecom-frontend-contract-test")
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    return TestClient(create_app(), raise_server_exceptions=False)


def _wecom_payload_from_html(html: str) -> dict:
    match = re.search(
        r'<script id="weComP1StatusPayload" type="application/json">\s*(.*?)\s*</script>',
        html,
        re.S,
    )
    assert match, html
    return json.loads(match.group(1))


def test_channels_page_renders_wecom_p1_external_config_status(monkeypatch) -> None:
    response = _client(monkeypatch).get("/admin/channels")
    html = response.text
    payload = _wecom_payload_from_html(html)

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert "weComP1StatusApp" in html
    assert "weComP1StatusPayload" in html
    assert "wecom_overview.js" in html
    assert payload["evidenceSummary"]["authStartStatus"] == "controlled_external_call_blocked_503"
    assert payload["evidenceSummary"]["authCallbackStatus"] == "controlled_external_call_blocked_503"
    assert payload["evidenceSummary"]["contactCallbackStatus"] == "fail_closed_400_missing_signature"
    assert payload["evidenceSummary"]["eventsStatus"] == "fail_closed_400_missing_signature"
    assert payload["evidenceSummary"]["callbackLinkedEvent"] == "not_found"
    assert payload["evidenceSummary"]["validCallbackSignature"] == "missing"
    assert payload["evidenceSummary"]["authRecord"] == "not_found"
    assert payload["evidenceSummary"]["permissionScope"] == "not_found"
    assert payload["evidenceSummary"]["realExternalCallExecuted"] is False
    assert payload["evidenceSummary"]["finalStatus"] == "BLOCKED_CONFIG_NOT_APPROVED"
    cards = payload["cards"]
    assert any(item["rawStatus"] == "external_config_blocked" for item in cards)
    assert any(item["rawStatus"] == "callback_fail_closed" for item in cards)
    assert any(item["rawStatus"] == "evidence_incomplete" for item in cards)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "已授权完成" not in serialized
    assert "callback_success" not in serialized
    assert "signature_verified" not in serialized
    assert "PASS_90_PLUS_CANDIDATE" not in serialized


def test_wecom_p1_slice_reuses_shared_status_and_interaction_contract() -> None:
    status_source = WECOM_STATUS.read_text(encoding="utf-8")
    overview_source = WECOM_OVERVIEW.read_text(encoding="utf-8")

    assert 'from "../shared/status_model.js"' in status_source
    assert 'from "../shared/interaction_contract.js"' in status_source
    assert 'from "../shared/status_card.js"' in overview_source
    assert '"external-config-blocked"' in status_source
    assert '"blocked"' in status_source
    assert '"evidence-incomplete"' in status_source
    assert '"operator-action-required"' in status_source
    assert '"failed-terminal"' in status_source
    assert '"pending"' in status_source
    assert "requires_external_config" in status_source
    assert "no_external_call" in status_source
    assert "no_production_write" in status_source
    assert "no_direct_send" in status_source
    assert 'validateDropIntent(scenario, "blocked_noop")' in status_source
    assert "Readonly preview only; no direct send." in overview_source


def test_wecom_p1_copy_does_not_claim_authorized_or_callback_success() -> None:
    status_source = WECOM_STATUS.read_text(encoding="utf-8")
    overview_source = WECOM_OVERVIEW.read_text(encoding="utf-8")

    assert "不能显示为授权完成" in status_source
    assert "不是回调成功" in status_source
    assert "不能显示为 complete" in status_source
    assert "不会触发真实授权、callback、渠道写入或外呼" in overview_source
    for forbidden in [
        "WeCom 已授权完成",
        "callback success 已完成",
        "signature verified 已完成",
        "permission scope complete",
        "PASS_90_PLUS_CANDIDATE",
    ]:
        assert forbidden not in status_source
        assert forbidden not in overview_source


def test_wecom_p1_rendered_fixture_does_not_expose_sensitive_strings(monkeypatch) -> None:
    response = _client(monkeypatch).get("/admin/channels")
    html = response.text

    for forbidden in [
        "raw_external_userid",
        "raw callback body",
        "raw_callback_body",
        "Authorization: Bearer",
        "access_token",
        "corpsecret",
        "suite_secret",
        "openid",
        "unionid",
        "13800138000",
    ]:
        assert forbidden not in html


def test_channel_template_mounts_wecom_p1_slice_without_replacing_channel_center() -> None:
    template = CHANNEL_TEMPLATE.read_text(encoding="utf-8")

    assert "weComP1StatusApp" in template
    assert "weComP1StatusPayload" in template
    assert "admin_console/p1/wecom/wecom_overview.js" in template
    assert 'data-channel-admission-page="channel-center"' in template
    assert "channel_code_center_next.js" in template
