from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from aicrm_next.admin_jobs.notification_settings import (
    FeishuWebhookValidationError,
    mask_webhook_url,
    validate_feishu_webhook_url,
)
from aicrm_next.admin_jobs.repository import build_admin_jobs_repository
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.setenv("SECRET_KEY", "next-admin-jobs-test")
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "internal-token")
    return TestClient(create_app(), raise_server_exceptions=False)


def _admin_action_token(html: str) -> str:
    match = re.search(r'name="admin_action_token" value="([^"]+)"', html)
    assert match, html[:1000]
    return match.group(1)


def test_admin_jobs_page_is_native_jobs_console(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/admin/jobs")
    html = response.text

    assert response.status_code == 200
    assert "同步与任务总览" in html
    for text in ["聊天同步", "回调状态", "消息批次", "待处理作业", "Webhook 投递", "群发队列"]:
        assert text in html
    assert "数据读取状态" not in html
    assert "production_unavailable" not in html
    assert "degraded" not in html


def test_admin_jobs_webhooks_tab_filters_retries_and_audits(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/admin/jobs?tab=webhooks&webhook_status=retry_scheduled")
    html = response.text
    token = _admin_action_token(html)

    assert response.status_code == 200
    assert "Webhook 投递状态" in html
    assert "执行到期重试" in html
    assert "ext-3" in html
    assert "Payload 摘要" in html

    retry = client.post(
        "/api/admin/jobs/webhook-deliveries/2/retry",
        json={"confirm": True, "admin_action_token": token, "operator": "tester-webhook"},
    )
    assert retry.status_code == 200
    assert retry.json()["ok"] is False
    assert retry.json()["reason"] == "webhook_not_configured"

    repo = build_admin_jobs_repository()
    assert repo.audit_logs[-1]["operator"] == "tester-webhook"
    assert repo.audit_logs[-1]["action_type"] == "retry_webhook_delivery"


def test_admin_broadcast_jobs_page_filters_and_actions(monkeypatch):
    client = _client(monkeypatch)

    page = client.get("/admin/broadcast-jobs?status=waiting_approval&source_type=campaign")
    html = page.text
    token = _admin_action_token(client.get("/admin/jobs?tab=webhooks").text)

    assert page.status_code == 200
    assert "群发任务队列" in html
    assert "审批通过" in html
    assert "取消" in html
    assert "campaign" in html
    assert "排队中内容" not in html

    approve = client.post(
        "/api/admin/broadcast-jobs/1/approve",
        json={"admin_action_token": token, "operator": "tester-broadcast"},
    )
    assert approve.status_code == 200
    assert approve.json()["job"]["status"] == "queued"
    assert approve.json()["job"]["approved_by"] == "tester-broadcast"

    cancel = client.post(
        "/api/admin/broadcast-jobs/2/cancel",
        json={"admin_action_token": token, "operator": "tester-broadcast", "reason": "manual stop"},
    )
    assert cancel.status_code == 200
    assert cancel.json()["job"]["status"] == "cancelled"
    assert cancel.json()["job"]["cancelled_by"] == "tester-broadcast"
    assert cancel.json()["job"]["cancel_reason"] == "manual stop"

    sent_cancel = client.post(
        "/api/admin/broadcast-jobs/3/cancel",
        json={"admin_action_token": token, "operator": "tester-broadcast"},
    )
    assert sent_cancel.status_code == 400
    assert "not cancelable" in sent_cancel.json()["error"]


def test_broadcast_queue_feishu_settings_page_module(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/admin/broadcast-jobs")
    html = response.text

    assert response.status_code == 200
    assert "飞书监控配置" in html
    assert "配置后，系统会每小时统计上一小时的群发任务" in html
    assert "data-feishu-webhook-input" in html
    assert "data-feishu-save" in html
    assert "data-feishu-validate" in html


def test_mask_webhook_url_safely_masks_feishu_and_lark_tokens():
    feishu = "https://open.feishu.cn/open-apis/bot/v2/hook/secret-token-abcd"
    lark = "https://open.larksuite.com/open-apis/bot/v2/hook/lark-secret-7890"

    assert mask_webhook_url(feishu) == "https://open.feishu.cn/open-apis/bot/v2/hook/****abcd"
    assert mask_webhook_url(lark) == "https://open.larksuite.com/open-apis/bot/v2/hook/****7890"
    assert mask_webhook_url("") is None
    assert mask_webhook_url("not a url") is None
    assert "secret-token" not in (mask_webhook_url(feishu) or "")
    assert "lark-secret" not in (mask_webhook_url(lark) or "")


def test_validate_feishu_webhook_url_accepts_only_official_https_hooks():
    for url in (
        "https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
        "https://open.larksuite.com/open-apis/bot/v2/hook/xxx",
    ):
        validate_feishu_webhook_url(url)

    rejected = (
        "http://open.feishu.cn/open-apis/bot/v2/hook/xxx",
        "https://example.com/open-apis/bot/v2/hook/xxx",
        "https://localhost/open-apis/bot/v2/hook/xxx",
        "https://127.0.0.1/open-apis/bot/v2/hook/xxx",
        "https://open.feishu.cn/open-apis/bot/v2/hook/",
        "",
        "not a url",
    )
    for url in rejected:
        with pytest.raises(FeishuWebhookValidationError):
            validate_feishu_webhook_url(url)


def test_broadcast_queue_feishu_settings_api_masks_saves_and_validates(monkeypatch):
    client = _client(monkeypatch)
    token = _admin_action_token(client.get("/admin/jobs?tab=webhooks").text)
    webhook = "https://open.feishu.cn/open-apis/bot/v2/hook/secret-token-abcd"

    no_token = client.put(
        "/api/admin/broadcast-jobs/notification-settings/feishu",
        json={"enabled": True, "webhookUrl": webhook},
    )
    assert no_token.status_code == 401

    unconfigured = client.get(
        "/api/admin/broadcast-jobs/notification-settings/feishu",
        headers={"X-Admin-Action-Token": token},
    )
    assert unconfigured.status_code == 200
    assert unconfigured.json()["validationStatus"] == "unconfigured"
    assert "secret-token" not in unconfigured.text

    saved = client.put(
        "/api/admin/broadcast-jobs/notification-settings/feishu",
        headers={"X-Admin-Action-Token": token},
        json={"enabled": True, "webhookUrl": webhook, "admin_action_token": token},
    )
    saved_payload = saved.json()
    assert saved.status_code == 200
    assert saved_payload["validationStatus"] == "unverified"
    assert saved_payload["webhookMasked"] == "https://open.feishu.cn/open-apis/bot/v2/hook/****abcd"
    assert "secret-token" not in saved.text

    captured: dict[str, str] = {}

    def fake_send(url: str, text: str) -> dict[str, object]:
        captured["url"] = url
        captured["text"] = text
        return {"ok": True}

    monkeypatch.setattr("aicrm_next.admin_jobs.notification_settings.send_feishu_webhook_message", fake_send)
    validated = client.post(
        "/api/admin/broadcast-jobs/notification-settings/feishu/validate",
        headers={"X-Admin-Action-Token": token},
        json={"enabled": True, "webhookUrl": webhook, "admin_action_token": token},
    )
    assert validated.status_code == 200
    assert validated.json()["ok"] is True
    assert validated.json()["validationStatus"] == "valid"
    assert validated.json()["webhookMasked"].endswith("****abcd")
    assert captured["url"] == webhook
    assert "群发队列监控验证" in captured["text"]
    assert "secret-token" not in validated.text

    get_after_validate = client.get(
        "/api/admin/broadcast-jobs/notification-settings/feishu",
        headers={"X-Admin-Action-Token": token},
    )
    assert get_after_validate.json()["validationStatus"] == "valid"
    assert "secret-token" not in get_after_validate.text


def test_broadcast_queue_feishu_validate_failure_does_not_leak_webhook(monkeypatch):
    client = _client(monkeypatch)
    token = _admin_action_token(client.get("/admin/jobs?tab=webhooks").text)
    webhook = "https://open.larksuite.com/open-apis/bot/v2/hook/top-secret-7890"

    monkeypatch.setattr(
        "aicrm_next.admin_jobs.notification_settings.send_feishu_webhook_message",
        lambda url, text: {"ok": False, "raw": {"url": url, "body": "large external body"}},
    )
    response = client.post(
        "/api/admin/broadcast-jobs/notification-settings/feishu/validate",
        headers={"X-Admin-Action-Token": token},
        json={"enabled": False, "webhookUrl": webhook, "admin_action_token": token},
    )

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["validationStatus"] == "invalid"
    assert response.json()["message"] == "飞书 webhook 验证失败，请检查地址或机器人配置"
    assert "top-secret" not in response.text
    assert "large external body" not in response.text

    setting = client.get(
        "/api/admin/broadcast-jobs/notification-settings/feishu",
        headers={"X-Admin-Action-Token": token},
    ).json()
    assert setting["validationStatus"] == "invalid"
    assert setting["enabled"] is False
    assert "top-secret" not in str(setting)


def test_admin_read_model_count_uses_identifier_not_percent_i(monkeypatch):
    psycopg = pytest.importorskip("psycopg")
    from aicrm_next.admin_read_model.repo import PostgresAdminReadRepository

    executed: list[object] = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, query, params=()):
            executed.append(query)
            assert "%I" not in str(query)
            self._row = {"table_oid": "sync_runs"} if "to_regclass" in str(query) else {"count": 7}

        def fetchone(self):
            return self._row

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def cursor(self):
            return Cursor()

    monkeypatch.setattr(psycopg, "connect", lambda *args, **kwargs: Connection())

    assert PostgresAdminReadRepository().count("sync_runs") == 7
    assert PostgresAdminReadRepository().count("outbound_webhook_deliveries") == 7
    assert PostgresAdminReadRepository().count("broadcast_jobs") == 7
