from __future__ import annotations

import re

from flask import Blueprint, Flask, render_template

from wecom_ability_service.domains.admin_dashboard import service as admin_dashboard_service


def test_admin_navigation_groups_and_marks_active_item(monkeypatch):
    monkeypatch.setattr(admin_dashboard_service, "_current_admin_role_codes", lambda: ["super_admin"])

    groups = admin_dashboard_service.list_admin_navigation("wechat_pay_transactions")

    assert [group["title"] for group in groups] == ["运营", "交易", "配置及后台"]
    operations = groups[0]["items"]
    operations_by_key = {item["key"]: item["label"] for item in operations}
    assert operations_by_key["customers"] == "客户激活 / 客户列表"
    assert operations_by_key["user_ops_funnel"] == "漏斗 / 数据看板"
    assert {item["key"]: item["label"] for item in groups[2]["items"]}["jobs"] == "同步任务配置 / 同步任务"
    trade_group = groups[1]
    assert trade_group["active"] is True
    assert [item["key"] for item in trade_group["items"]] == ["wechat_pay_transactions"]
    assert {item["key"]: item["active"] for item in trade_group["items"]} == {
        "wechat_pay_transactions": True,
    }
    assert all(group["title"] != "素材" for group in groups)


def test_admin_navigation_filters_empty_groups_by_role(monkeypatch):
    monkeypatch.setattr(admin_dashboard_service, "_current_admin_role_codes", lambda: ["questionnaire_admin"])

    groups = admin_dashboard_service.list_admin_navigation("questionnaires")

    assert [group["title"] for group in groups] == ["运营", "配置及后台"]
    assert groups[0]["active"] is True
    assert groups[0]["items"] == [
        {
            "key": "questionnaires",
            "label": "问卷",
            "endpoint": "api.admin_console_questionnaires",
            "active": True,
        }
    ]
    assert [item["key"] for item in groups[1]["items"]] == ["api_docs"]


def test_automation_admin_navigation_excludes_retired_material_group(monkeypatch):
    monkeypatch.setattr(admin_dashboard_service, "_current_admin_role_codes", lambda: ["automation_admin"])

    groups = admin_dashboard_service.list_admin_navigation("attachment_library")

    assert [group["title"] for group in groups] == ["运营", "配置及后台"]
    assert all(
        item["key"] not in {"image_library", "miniprogram_library", "attachment_library"}
        for group in groups
        for item in group["items"]
    )
    assert all(group["active"] is False for group in groups)


def test_admin_base_template_renders_grouped_navigation():
    app = Flask(
        __name__,
        template_folder="../wecom_ability_service/templates",
        static_folder="../wecom_ability_service/static",
    )
    api = Blueprint("api", __name__)
    for endpoint, path in {
        "admin_dashboard_shell_context": "/api/admin/dashboard/shell-context",
        "admin_automation_conversion": "/admin/automation-conversion",
        "admin_cloud_orchestrator_workspace": "/admin/cloud-orchestrator",
        "admin_console_customers": "/admin/customers",
        "admin_hxc_dashboard_workspace": "/admin/user-ops",
        "admin_console_questionnaires": "/admin/questionnaires",
        "admin_wecom_tags_page": "/admin/wecom-tags",
        "admin_wechat_pay_transactions_page": "/admin/wechat-pay/transactions",
        "admin_console_jobs": "/admin/jobs",
        "admin_config_home": "/admin/config",
        "admin_console_api_docs": "/admin/api-docs",
    }.items():
        api.add_url_rule(path, endpoint, lambda: "")
    app.register_blueprint(api)

    with app.test_request_context("/admin/wechat-pay/transactions"):
        html = render_template(
            "admin_console/base.html",
            page_title="交易管理",
            page_summary="",
            breadcrumbs=[],
            nav_items=admin_dashboard_service.list_admin_navigation("wechat_pay_transactions"),
            shell_status={},
            current_admin_user=None,
            show_shell_meta=False,
            page_notice="",
            page_error="",
        )

    assert re.search(
        r'class="admin-nav-section is-active">\s*<div class="admin-nav-section-title">交易</div>',
        html,
    )
    assert re.search(r'class="admin-nav-link is-active"\s+href="/admin/wechat-pay/transactions"', html)
    assert '<div class="admin-nav-section-title">运营</div>' in html
    assert "客户激活 / 客户列表" in html
    assert "漏斗 / 数据看板" in html
    assert "同步任务配置 / 同步任务" in html
    assert "图片素材库" not in html
    assert "小程序素材库" not in html
    assert "附件素材库" not in html
    assert "商品管理" not in html
