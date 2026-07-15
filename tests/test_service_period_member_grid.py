from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os

import pytest
from fastapi.testclient import TestClient

from aicrm_next.commerce.repo import reset_commerce_fixture_state
from aicrm_next.main import create_app
from aicrm_next.service_period.application import (
    CreateServicePeriodProductCommand,
    GrantOrRenewEntitlementCommand,
)
from aicrm_next.service_period.dto import ServicePeriodProductCreateRequest
from aicrm_next.service_period.member_grid import (
    MemberViewConflictError,
    empty_view_config,
    member_grid_schema,
    normalize_view_config,
    query_in_memory_rows,
)
from aicrm_next.service_period.repo import (
    PostgresServicePeriodRepository,
    build_service_period_repository,
    reset_service_period_fixture_state,
)
from aicrm_next.shared.errors import ContractError
from tests.admin_auth_test_helpers import install_admin_action_tokens, install_admin_session


def _reset() -> None:
    reset_commerce_fixture_state()
    reset_service_period_fixture_state()


def _product_payload(code: str = "sp_member_grid") -> dict:
    return {
        "product_code": code,
        "title": "成员网格测试商品",
        "description": "飞书式原生成员网格",
        "price_cents": 99900,
        "currency": "CNY",
        "status": "active",
        "duration_days": 90,
        "membership_config_id": "member_grid_vip",
        "membership_config_name": "成员网格会员",
    }


def _paid_order(index: int, *, product_code: str = "sp_member_grid") -> dict:
    return {
        "id": 10000 + index,
        "out_trade_no": f"SP_MEMBER_GRID_{index:04d}",
        "product_code": product_code,
        "product_name": "成员网格测试商品",
        "amount_total": 99900,
        "currency": "CNY",
        "unionid": f"union_grid_{index:04d}",
        "payer_name_snapshot": f"会员 {index:04d}",
        "status": "paid",
        "trade_state": "SUCCESS",
        "paid_at": "2099-01-01T00:00:00+00:00",
        "metadata_json": {"payer_identity": {"external_userid": f"wm_grid_{index:04d}"}},
    }


def _member(index: int, *, now: datetime) -> dict:
    matched = index % 4 != 0
    progress = None if index % 5 == 0 else {"current": index % 6, "total": 5}
    return {
        "record_id": index,
        "unionid": f"union_{index:04d}",
        "display_name": f"会员 {index:04d}",
        "external_userid": f"wm_{index:04d}",
        "end_at": (now + timedelta(days=index % 30)).isoformat(),
        "remark": "重点" if index % 7 == 0 else "",
        "huangyoucan_match_status": "matched_unionid" if matched else "not_found",
        "huangyoucan_formally_logged_in": index % 2 == 0,
        "huangyoucan_has_token_usage": index % 3 == 0,
        "huangyoucan_learning_plan_progress": progress,
        "huangyoucan_open_count_7d": index % 11,
        "huangyoucan_last_open_at": (now - timedelta(hours=index)).isoformat() if matched else None,
    }


def test_member_grid_schema_is_code_owned_and_fixed_to_eight_fields() -> None:
    schema = member_grid_schema()

    assert [field["id"] for field in schema["fields"]] == [
        "member",
        "remaining_days",
        "formally_logged_in",
        "token_usage",
        "learning_plan_progress",
        "open_count_7d",
        "last_open_at",
        "remark",
    ]
    assert schema["limits"] == {
        "filter_conditions": 20,
        "sorts": 8,
        "groups": 2,
        "page_size": 100,
    }
    assert schema["fields"][-1]["editable"] is True
    assert all(not field["editable"] for field in schema["fields"][:-1])


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (lambda config: config["sorts"].append({"field": "unknown", "direction": "asc"}), "不支持的字段"),
        (
            lambda config: config["filter"]["conditions"].append(
                {"field": "member", "operator": "raw_sql", "value": "1=1"}
            ),
            "不支持操作符",
        ),
        (
            lambda config: config["sorts"].extend(
                [{"field": "member", "direction": "asc"}, {"field": "member", "direction": "desc"}]
            ),
            "不能重复",
        ),
        (
            lambda config: (
                config["sorts"].append({"field": "member", "direction": "asc"}),
                config["groups"].append({"field": "member", "direction": "asc"}),
            ),
            "不能重复参与排序",
        ),
    ),
)
def test_member_grid_rejects_unknown_fields_operators_and_duplicate_ordering(mutate, message: str) -> None:
    config = empty_view_config()
    mutate(config)

    with pytest.raises(ContractError, match=message):
        normalize_view_config(config)


def test_member_grid_and_or_filter_sort_two_level_group_and_progress_semantics(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    now = datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc)
    members = [_member(index, now=now) for index in range(1, 61)]
    config = empty_view_config()
    config["filter"] = {
        "logic": "and",
        "conditions": [
            {"field": "remaining_days", "operator": "gte", "value": 10},
            {"field": "learning_plan_progress", "operator": "state_in", "value": ["in_progress", "complete"]},
        ],
    }
    config["groups"] = [
        {"field": "formally_logged_in", "direction": "asc"},
        {"field": "token_usage", "direction": "asc"},
    ]
    config["sorts"] = [{"field": "learning_plan_progress", "direction": "desc"}]

    payload = query_in_memory_rows(members, config=config, limit=100)

    assert payload["rows"]
    assert all(row["values"]["remaining_days"] >= 10 for row in payload["rows"])
    assert all(row["values"]["learning_plan_progress"]["state"] in {"in_progress", "complete"} for row in payload["rows"])
    assert all(len(row["group_path"]) == 2 for row in payload["rows"])
    assert all(path["count"] > 0 for row in payload["rows"] for path in row["group_path"])

    or_config = empty_view_config()
    or_config["filter"] = {
        "logic": "or",
        "conditions": [
            {"field": "member", "operator": "equals", "value": "会员 0001"},
            {"field": "remark", "operator": "contains", "value": "重点"},
        ],
    }
    or_payload = query_in_memory_rows(members, config=or_config, limit=100)
    unionids = {row["unionid"] for row in or_payload["rows"]}
    assert "union_0001" in unionids
    assert "union_0007" in unionids


def test_signed_keyset_cursor_has_no_cross_page_duplicates_and_rejects_tampering(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    now = datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc)
    members = [_member(index, now=now) for index in range(1, 236)]
    config = empty_view_config()
    config["groups"] = [{"field": "formally_logged_in", "direction": "asc"}]
    config["sorts"] = [{"field": "member", "direction": "asc"}]

    first = query_in_memory_rows(members, config=config, limit=100)
    second = query_in_memory_rows(members, config=config, limit=100, cursor=first["next_cursor"])
    third = query_in_memory_rows(members, config=config, limit=100, cursor=second["next_cursor"])
    record_ids = [row["record_id"] for page in (first, second, third) for row in page["rows"]]

    assert len(record_ids) == 235
    assert len(set(record_ids)) == 235
    assert first["total"] == 235
    assert third["next_cursor"] == ""

    tampered = first["next_cursor"][:-1] + ("A" if first["next_cursor"][-1] != "A" else "B")
    with pytest.raises(ContractError, match="分页游标无效"):
        query_in_memory_rows(members, config=config, cursor=tampered)
    changed = empty_view_config()
    changed["sorts"] = [{"field": "member", "direction": "desc"}]
    with pytest.raises(ContractError, match="视图配置已变化"):
        query_in_memory_rows(members, config=changed, cursor=first["next_cursor"])


def test_shared_view_crud_name_conflict_optimistic_lock_and_copy_default_only(next_client) -> None:
    _reset()
    created = next_client.post("/api/admin/service-period-products", json=_product_payload())
    product = created.json()["product"]

    initial = next_client.get(f"/api/admin/service-period-products/{product['id']}/member-views")
    assert initial.status_code == 200
    assert [(item["name"], item["is_default"]) for item in initial.json()["items"]] == [("表格", True)]

    config = empty_view_config()
    config["sorts"] = [{"field": "remaining_days", "direction": "asc"}]
    custom = next_client.post(
        f"/api/admin/service-period-products/{product['id']}/member-views",
        json={"name": "到期优先", "config": config},
    )
    assert custom.status_code == 201
    view = custom.json()["view"]
    assert view["version"] == 1

    duplicate = next_client.post(
        f"/api/admin/service-period-products/{product['id']}/member-views",
        json={"name": "到期优先".upper(), "config": config},
    )
    assert duplicate.status_code == 409

    updated_config = empty_view_config()
    updated_config["groups"] = [{"field": "formally_logged_in", "direction": "asc"}]
    updated = next_client.put(
        f"/api/admin/service-period-products/{product['id']}/member-views/{view['id']}",
        json={"name": "登录分组", "config": updated_config, "version": 1},
    )
    assert updated.status_code == 200
    assert updated.json()["view"]["version"] == 2

    stale = next_client.put(
        f"/api/admin/service-period-products/{product['id']}/member-views/{view['id']}",
        json={"name": "过期保存", "config": config, "version": 1},
    )
    assert stale.status_code == 409

    default_view = initial.json()["items"][0]
    default_delete = next_client.request(
        "DELETE",
        f"/api/admin/service-period-products/{product['id']}/member-views/{default_view['id']}",
        json={"version": default_view["version"]},
    )
    assert default_delete.status_code == 400

    copied = next_client.post(f"/api/admin/service-period-products/{product['id']}/copy")
    assert copied.status_code == 201
    copied_id = copied.json()["product"]["id"]
    copied_views = next_client.get(f"/api/admin/service-period-products/{copied_id}/member-views").json()["items"]
    assert [(item["name"], item["is_default"]) for item in copied_views] == [("表格", True)]


def test_member_grid_api_uses_real_entitlement_rows_and_reuses_remark_endpoint(next_client) -> None:
    _reset()
    product = CreateServicePeriodProductCommand()(ServicePeriodProductCreateRequest(**_product_payload()))["product"]
    GrantOrRenewEntitlementCommand()(order=_paid_order(1))

    queried = next_client.post(
        f"/api/admin/service-period-products/{product['id']}/member-grid/query",
        json={"config": empty_view_config(), "limit": 100},
    )
    assert queried.status_code == 200
    row = queried.json()["rows"][0]
    assert row["unionid"] == "union_grid_0001"
    assert row["values"]["member"]["primary"] == "会员 0001"
    assert row["values"]["member"]["secondary"] == "wm_grid_0001"
    assert list(row["values"]) == [
        "member",
        "remaining_days",
        "formally_logged_in",
        "token_usage",
        "learning_plan_progress",
        "open_count_7d",
        "last_open_at",
        "remark",
    ]

    remark = next_client.put(
        f"/api/admin/service-period-products/{product['id']}/members/union_grid_0001/remark",
        json={"remark": "网格内备注"},
    )
    assert remark.status_code == 200
    refreshed = next_client.post(
        f"/api/admin/service-period-products/{product['id']}/member-grid/query",
        json={"config": empty_view_config(), "limit": 100},
    )
    assert refreshed.json()["rows"][0]["values"]["remark"] == "网格内备注"


def test_viewer_can_query_drafts_but_cannot_manage_views_or_edit_remarks(monkeypatch) -> None:
    _reset()
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_ROUTE_POLICY_ENFORCED", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    client = TestClient(create_app(), raise_server_exceptions=False)
    product = CreateServicePeriodProductCommand()(ServicePeriodProductCreateRequest(**_product_payload("sp_grid_permissions")))["product"]
    GrantOrRenewEntitlementCommand()(order=_paid_order(1, product_code="sp_grid_permissions"))
    query_target = "/api/admin/service-period-products/{service_product_id}/member-grid/query"
    query_token = install_admin_action_tokens(client, ("POST", query_target), roles=("viewer",))[("POST", query_target)]

    schema = client.get(f"/api/admin/service-period-products/{product['id']}/member-grid/schema")
    views = client.get(f"/api/admin/service-period-products/{product['id']}/member-views")
    query = client.post(
        f"/api/admin/service-period-products/{product['id']}/member-grid/query",
        headers={"X-Admin-Action-Token": query_token},
        json={"config": empty_view_config()},
    )
    denied_create = client.post(
        f"/api/admin/service-period-products/{product['id']}/member-views",
        headers={"X-Admin-Action-Token": query_token},
        json={"name": "viewer", "config": empty_view_config()},
    )
    denied_remark = client.put(
        f"/api/admin/service-period-products/{product['id']}/members/union_grid_0001/remark",
        headers={"X-Admin-Action-Token": query_token},
        json={"remark": "viewer cannot write"},
    )

    assert [schema.status_code, views.status_code, query.status_code] == [200, 200, 200]
    assert denied_create.status_code == 403
    assert denied_remark.status_code == 403

    page = client.get(f"/admin/service-period-products/{product['id']}/data")
    grants_text = page.text.split('id="aicrmAdminActionGrants"', 1)[1]
    assert query_target in grants_text
    assert "POST /api/admin/service-period-products/{service_product_id}/member-views" not in grants_text
    assert "PUT /api/admin/service-period-products/{service_product_id}/members/{unionid}/remark" not in grants_text


def test_postgres_grid_query_and_view_repository_contract(next_pg_schema) -> None:
    import psycopg

    database_url = os.environ["DATABASE_URL"]
    repo = PostgresServicePeriodRepository(database_url)
    with psycopg.connect(database_url) as connection:
        trade_product_id = connection.execute(
            """
            INSERT INTO wechat_pay_products (product_code, name, amount_total, currency, status, enabled)
            VALUES ('sp_grid_pg', 'PG 成员网格', 99900, 'CNY', 'active', TRUE)
            RETURNING id
            """
        ).fetchone()[0]
    product = repo.create_service_product(
        trade_product={"id": trade_product_id, "product_code": "sp_grid_pg", "title": "PG 成员网格"},
        duration_days=90,
        membership_config_id="pg_grid",
        membership_config_name="PG 网格会员",
        link_slug="sp-grid-pg",
    )
    with psycopg.connect(database_url) as connection:
        for index in range(1, 231):
            unionid = f"union_grid_pg_{index:04d}"
            connection.execute(
                """
                INSERT INTO service_period_entitlements (
                    service_product_id, trade_product_id, unionid, external_userid_snapshot,
                    membership_config_id, status, start_at, end_at, metadata_json
                ) VALUES (%s, %s, %s, %s, 'pg_grid', 'active', CURRENT_TIMESTAMP,
                          CURRENT_TIMESTAMP + (%s * INTERVAL '1 day'), %s::jsonb)
                """,
                (
                    int(product["id"]),
                    trade_product_id,
                    unionid,
                    f"wm_grid_pg_{index:04d}",
                    index % 90 + 1,
                    json.dumps({"payer_name": f"PG 会员 {index:04d}"}, ensure_ascii=False),
                ),
            )
            connection.execute(
                """
                INSERT INTO service_period_huangyoucan_usage_snapshot (
                    huangyoucan_user_id, unionid, mobile_md5, formally_logged_in, has_token_usage,
                    learning_plan_id, learning_plan_current, learning_plan_total,
                    open_count_7d, last_open_at, refreshed_at
                ) VALUES (%s, %s, '', %s, %s, 'pg_plan', %s, 5, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (f"hyc_grid_pg_{index:04d}", unionid, index % 2 == 0, index % 3 == 0, index % 6, index % 11),
            )

    views = repo.list_member_views(product["id"])["items"]
    assert [(view["name"], view["is_default"]) for view in views] == [("表格", True)]
    created_view = repo.create_member_view(product["id"], name="PG 分组", config=empty_view_config(), actor="pytest")["view"]
    updated_view = repo.update_member_view(
        product["id"],
        created_view["id"],
        name="PG 两层分组",
        config={
            **empty_view_config(),
            "groups": [
                {"field": "formally_logged_in", "direction": "asc"},
                {"field": "token_usage", "direction": "asc"},
            ],
            "sorts": [{"field": "member", "direction": "asc"}],
        },
        expected_version=1,
        actor="pytest",
    )["view"]
    assert updated_view["version"] == 2
    with pytest.raises(MemberViewConflictError):
        repo.update_member_view(
            product["id"],
            created_view["id"],
            name="stale",
            config=empty_view_config(),
            expected_version=1,
            actor="pytest",
        )

    config = updated_view["config"]
    pages = []
    cursor = ""
    while True:
        page = repo.query_member_grid(product["id"], config=config, limit=100, cursor=cursor)
        pages.append(page)
        cursor = page["next_cursor"]
        if not cursor:
            break
    rows = [row for page in pages for row in page["rows"]]
    assert len(rows) == 230
    assert len({row["record_id"] for row in rows}) == 230
    assert pages[0]["total"] == 230
    assert all(len(row["group_path"]) == 2 for row in rows)
