from __future__ import annotations

from aicrm_next.channel_entry.wecom_adapter import (
    ProductionWeComAdapter,
    describe_wecom_adapter,
    set_wecom_adapter,
)


class _Response:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _HTTP:
    def __init__(self) -> None:
        self.get_calls: list[dict] = []
        self.post_calls: list[dict] = []

    def get(self, url, *, params, timeout):
        self.get_calls.append({"url": url, "params": params, "timeout": timeout})
        return _Response({"errcode": 0, "access_token": "token-real", "expires_in": 7200})

    def post(self, url, *, params, json, timeout):
        self.post_calls.append({"url": url, "params": params, "json": json, "timeout": timeout})
        if url.endswith("/add_contact_way"):
            return _Response({"errcode": 0, "config_id": "cfg-1", "qr_code": "https://wework.qpic.cn/qr"})
        return _Response({"errcode": 0, "errmsg": "ok"})


def _set_required_env(monkeypatch):
    monkeypatch.setenv("WECOM_CORP_ID", "ww-real")
    monkeypatch.setenv("WECOM_CONTACT_SECRET", "secret-real")
    monkeypatch.setenv("WECOM_CALLBACK_TOKEN", "token")
    monkeypatch.setenv("WECOM_CALLBACK_AES_KEY", "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG")


def test_wecom_adapter_diagnosis_reports_disabled_and_missing_config(monkeypatch):
    set_wecom_adapter(None)
    for name in ("WECOM_CORP_ID", "WECOM_CONTACT_SECRET", "WECOM_SECRET", "WECOM_CALLBACK_TOKEN", "WECOM_CALLBACK_AES_KEY", "AICRM_NEXT_WECOM_REAL_CALLS_ENABLED"):
        monkeypatch.delenv(name, raising=False)

    missing = describe_wecom_adapter()
    assert missing["real_wecom_adapter_enabled"] is False
    assert missing["real_wecom_adapter_reason"] == "missing_config"
    assert "WECOM_CORP_ID" in missing["missing_config"]

    _set_required_env(monkeypatch)
    disabled = describe_wecom_adapter()
    assert disabled["real_wecom_adapter_enabled"] is False
    assert disabled["real_wecom_adapter_reason"] == "real_calls_disabled"
    assert disabled["can_send_welcome"] is False
    assert disabled["can_mark_tag"] is False
    assert disabled["can_create_contact_way"] is False


def test_production_wecom_adapter_uses_official_external_contact_payloads(monkeypatch):
    set_wecom_adapter(None)
    _set_required_env(monkeypatch)
    http = _HTTP()
    adapter = ProductionWeComAdapter(http=http, timeout=3)

    welcome = adapter.send_welcome_msg({"welcome_code": "wc-1", "text": {"content": "hi"}})
    tag = adapter.mark_external_contact_tags(
        external_userid="wm-1",
        follow_user_userid="owner-1",
        add_tags=["tag-1"],
        remove_tags=["tag-old"],
    )
    qrcode = adapter.create_contact_way({"type": 2, "scene": 2, "state": "aqr_260531_abcd", "user": ["owner-1"]})
    detail = adapter.get_external_contact_detail("wm-1")

    assert welcome["errcode"] == 0
    assert tag["errcode"] == 0
    assert qrcode["config_id"] == "cfg-1"
    assert detail["errcode"] == 0
    assert http.get_calls[0]["url"].endswith("/cgi-bin/gettoken")
    assert http.get_calls[0]["params"] == {"corpid": "ww-real", "corpsecret": "secret-real"}
    assert [call["url"].rsplit("/", 1)[-1] for call in http.post_calls] == ["send_welcome_msg", "mark_tag", "add_contact_way"]
    assert http.post_calls[1]["json"] == {
        "userid": "owner-1",
        "external_userid": "wm-1",
        "add_tag": ["tag-1"],
        "remove_tag": ["tag-old"],
    }
    assert http.post_calls[2]["json"]["state"] == "aqr_260531_abcd"
