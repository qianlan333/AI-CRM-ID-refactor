from __future__ import annotations

from datetime import datetime
from io import BytesIO
from zipfile import ZipFile

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.routes import _process_external_contact_event
from wecom_ability_service.services import (
    log_external_contact_event,
    refresh_contact_tags_for_external_userid,
    schedule_user_ops_auto_assign_class_term_job,
    sync_user_ops_class_term_tag_definitions,
)


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "user-ops.sqlite3"
    private_key_path = tmp_path / "wecom_private_key.pem"
    sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key_path.write_text("fake-key", encoding="utf-8")
    sdk_lib_path.write_text("fake-so", encoding="utf-8")

    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(db_path),
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
            "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
        }
    )
    with app.app_context():
        init_db()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def _seed_user_ops_sources(app) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?), (?, ?, ?, ?)
            """,
            ("sales_01", "ZhaoYanFang", "sales", True, "sales_02", "QianLan", "sales", True),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?)
            """,
            (
                "wm_signed_999",
                "已报999用户",
                "sales_01",
                "",
                "wm_signed_999",
                now,
                "wm_signed_3999",
                "已报3999用户",
                "sales_02",
                "",
                "wm_signed_3999",
                now,
                "wm_lead_bound",
                "已绑定引流用户",
                "sales_01",
                "",
                "wm_lead_bound",
                now,
            ),
        )
        db.execute(
            """
            INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (1, "13800138000", "tp-001", 2, "13800138002", "tp-002"),
        )
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                   (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "wm_signed_999",
                1,
                "sales_01",
                "sales_01",
                "sales_01",
                "wm_lead_bound",
                2,
                "sales_01",
                "sales_01",
                "sales_01",
            ),
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot,
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?),
                   (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            """,
            (
                "wm_signed_999",
                "signed_999",
                "已报名999",
                "999快照用户",
                "sales_01",
                "13800138000",
                "sales_01",
                "success",
                "",
                "{}",
                "wm_signed_3999",
                "signed_3999",
                "已报名3999",
                "3999快照用户",
                "sales_02",
                "13800138001",
                "sales_02",
                "success",
                "",
                "{}",
            ),
        )
        db.commit()


def _insert_contact_tags(app, rows: list[tuple[str, str, str, str]]) -> None:
    with app.app_context():
        db = get_db()
        for external_userid, userid, tag_id, tag_name in rows:
            db.execute(
                """
                INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name)
                VALUES (?, ?, ?, ?)
                """,
                (external_userid, userid, tag_id, tag_name),
            )
        db.commit()


def _seed_zhao_contact(
    app,
    *,
    external_userid: str,
    customer_name: str = "赵顾问新客",
) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with app.app_context():
        db = get_db()
        existing_owner = db.execute(
            "SELECT 1 FROM owner_role_map WHERE userid = ? LIMIT 1",
            ("ZhaoYanFang",),
        ).fetchone()
        if not existing_owner:
            db.execute(
                """
                INSERT INTO owner_role_map (userid, display_name, role, active)
                VALUES (?, ?, ?, ?)
                """,
                ("ZhaoYanFang", "ZhaoYanFang", "sales", True),
            )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                external_userid,
                customer_name,
                "ZhaoYanFang",
                "",
                external_userid,
                now,
            ),
        )
        db.commit()


def _build_external_contact_detail(
    *,
    external_userid: str,
    owner_userid: str,
    customer_name: str = "回调客户",
    follow_user_tags: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "external_contact": {
            "external_userid": external_userid,
            "name": customer_name,
            "unionid": f"union-{external_userid}",
            "openid": f"openid-{external_userid}",
        },
        "follow_user": [
            {
                "userid": owner_userid,
                "remark": "",
                "description": external_userid,
                "tags": list(follow_user_tags or []),
            }
        ],
    }


class _FakeCallbackContactClient:
    def __init__(self, detail: dict[str, object]):
        self._detail = detail

    def get_contact(self, external_userid: str) -> dict[str, object]:
        assert external_userid == self._detail["external_contact"]["external_userid"]
        return dict(self._detail)

    def update_contact_description(self, payload: dict[str, object]) -> dict[str, object]:
        return {"errcode": 0, "errmsg": "ok", **payload}


def _build_corp_tag_payload(
    tags: list[tuple[str, str]],
    *,
    group_name: str = "9.9元改变计划",
    group_id: str = "group-term",
) -> dict[str, object]:
    return {
        "tag_group": [
            {
                "group_name": group_name,
                "group_id": group_id,
                "tag": [{"id": tag_id, "name": tag_name} for tag_id, tag_name in tags],
            }
        ]
    }


class _FakeUserOpsContactClient:
    def __init__(
        self,
        *,
        corp_tag_payload: dict[str, object] | None = None,
        contact_details: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self._corp_tag_payload = corp_tag_payload or _build_corp_tag_payload(
            [
                ("tag-term-1", "首期7天改变计划"),
                ("tag-term-3", "0322改变计划-第3期"),
                ("tag-term-4", "0330改变计划-第4期"),
            ]
        )
        self._contact_details = dict(contact_details or {})

    def set_contact_detail(self, external_userid: str, detail: dict[str, object]) -> None:
        self._contact_details[external_userid] = detail

    def list_external_contact_tags(self, payload: dict[str, object] | None = None) -> dict[str, object]:
        return dict(self._corp_tag_payload)

    def get_contact(self, external_userid: str) -> dict[str, object]:
        if external_userid not in self._contact_details:
            return _build_external_contact_detail(
                external_userid=external_userid,
                owner_userid="",
                follow_user_tags=[],
            )
        return dict(self._contact_details[external_userid])


@pytest.fixture()
def user_ops_contact_client(monkeypatch):
    fake_client = _FakeUserOpsContactClient()
    monkeypatch.setattr("wecom_ability_service.services._user_ops_contact_client", lambda: fake_client)
    return fake_client


def _build_test_xlsx(rows: list[list[str] | str]) -> bytes:
    normalized_rows: list[list[str]] = []
    shared_values: list[str] = []
    for row in rows:
        if isinstance(row, str):
            normalized = [row]
        else:
            normalized = [str(item) for item in row]
        normalized_rows.append(normalized)
        shared_values.extend(normalized)
    shared_strings = "".join(f"<si><t>{value}</t></si>" for value in shared_values)
    sheet_rows = []
    shared_index = 0
    for row_index, row in enumerate(normalized_rows, start=1):
        cells = []
        for column_index, _ in enumerate(row, start=1):
            column_name = chr(64 + column_index)
            cells.append(f'<c r="{column_name}{row_index}" t="s"><v>{shared_index}</v></c>')
            shared_index += 1
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f"{shared_strings}"
                "</sst>"
            ),
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                "<sheetData>"
                f"{''.join(sheet_rows)}"
                "</sheetData>"
                "</worksheet>"
            ),
        )
    return buffer.getvalue()


def test_reload_user_ops_pool_materializes_existing_crm_data(client, app):
    _seed_user_ops_sources(app)

    response = client.post("/api/admin/user-ops/reload")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["total"] == 3

    with app.app_context():
        rows = get_db().execute(
            """
            SELECT external_userid, mobile, current_status, is_wecom_bound, owner_userid
            FROM user_ops_pool_current
            ORDER BY external_userid ASC
            """
        ).fetchall()
        assert len(rows) == 3
        assert rows[0]["external_userid"] == "wm_lead_bound"
        assert rows[0]["current_status"] == "lead_trial"
        assert bool(rows[0]["is_wecom_bound"]) is True
        assert rows[1]["external_userid"] == "wm_signed_3999"
        assert rows[1]["mobile"] == "13800138001"
        assert bool(rows[1]["is_wecom_bound"]) is False
        assert rows[2]["external_userid"] == "wm_signed_999"
        assert rows[2]["owner_userid"] == "sales_01"


def test_user_ops_overview_counts_are_correct(client, app):
    _seed_user_ops_sources(app)
    client.post("/api/admin/user-ops/reload")

    response = client.get("/api/admin/user-ops/overview")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["total_users"] == 3
    assert payload["lead_trial_count"] == 1
    assert payload["signed_999_count"] == 1
    assert payload["signed_3999_count"] == 1
    assert payload["wecom_bound_count"] == 2
    assert payload["wecom_unbound_count"] == 1


def test_user_ops_list_filters_by_current_status(client, app):
    _seed_user_ops_sources(app)
    client.post("/api/admin/user-ops/reload")

    response = client.get("/api/admin/user-ops/list?current_status=signed_999")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["total"] == 1
    assert payload["items"][0]["external_userid"] == "wm_signed_999"
    assert payload["items"][0]["current_status"] == "signed_999"


def test_user_ops_list_filters_by_is_wecom_bound(client, app):
    _seed_user_ops_sources(app)
    client.post("/api/admin/user-ops/reload")

    response = client.get("/api/admin/user-ops/list?is_wecom_bound=true")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["total"] == 2
    assert {item["external_userid"] for item in payload["items"]} == {"wm_signed_999", "wm_lead_bound"}


def test_user_ops_list_filters_by_owner_userid(client, app):
    _seed_user_ops_sources(app)
    client.post("/api/admin/user-ops/reload")

    response = client.get("/api/admin/user-ops/list?owner_userid=sales_01")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["total"] == 2
    assert {item["external_userid"] for item in payload["items"]} == {"wm_signed_999", "wm_lead_bound"}


def test_user_ops_export_returns_current_pool_rows(client, app):
    _seed_user_ops_sources(app)
    client.post("/api/admin/user-ops/reload")

    response = client.get("/api/admin/user-ops/export?owner_userid=sales_01")
    content = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.mimetype == "application/vnd.ms-excel"
    assert "已报999用户" in content or "999快照用户" in content
    assert "已绑定引流用户" in content


def test_user_ops_history_returns_reload_records(client, app):
    _seed_user_ops_sources(app)
    client.post("/api/admin/user-ops/reload")

    response = client.get("/api/admin/user-ops/history")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert isinstance(payload["items"], list)
    assert payload["total"] >= 3
    assert payload["items"][0]["action_type"] in {"pool_reload_upsert", "pool_reload_remove"}


def test_user_ops_ui_route_exists(client):
    response = client.get("/admin/user-ops/ui")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "统一用户运营看板 v2" in html
    assert "已激活 / 未激活" in html
    assert 'id="open-class-term-import-modal-btn"' in html
    assert 'id="open-activation-import-modal-btn"' in html


def test_user_ops_ui_hides_legacy_fields_and_buttons(client):
    response = client.get("/admin/user-ops/ui")
    html = response.get_data(as_text=True)
    page_shell = html.split('<div id="class-term-import-modal-backdrop"', 1)[0]

    assert response.status_code == 200
    assert "导入学员" in page_shell
    assert "导入黄小璨激活状态" in page_shell
    assert 'id="open-class-term-import-modal-btn"' in page_shell
    assert 'id="open-activation-import-modal-btn"' in page_shell
    assert 'id="class-term-import-text"' not in page_shell
    assert 'id="class-term-import-file"' not in page_shell
    assert 'id="activation-import-text"' not in page_shell
    assert 'id="activation-import-file"' not in page_shell
    assert "班期回填" not in page_shell
    assert "执行待处理自动归班任务" not in page_shell
    assert "检查标签" not in page_shell
    assert html.count('<section class="panel toolbar">') == 1
    assert 'id="class-term-import-modal-backdrop" class="modal-backdrop hidden"' in html
    assert 'id="activation-import-modal-backdrop" class="modal-backdrop hidden"' in html
    assert '<label for="filter-current-status">当前状态</label>' not in html
    assert '<label for="filter-owner">跟进人</label>' not in html
    assert "<th>当前状态</th>" not in html
    assert "<th>跟进人</th>" not in html
    assert "<th>高意向备注</th>" not in html
    assert "<th>更新时间</th>" not in html


def test_user_ops_ui_prioritizes_phone_bound_class_term_activation_columns(client):
    response = client.get("/admin/user-ops/ui")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    phone_index = html.index("<th>手机号</th>")
    bound_index = html.index("<th>是否加微</th>")
    class_term_index = html.index("<th>班期</th>")
    activation_index = html.index("<th>激活状态</th>")
    customer_name_index = html.index("<th>客户昵称</th>")
    external_index = html.index("<th>external_userid</th>")

    assert phone_index < bound_index < class_term_index < activation_index < customer_name_index < external_index


def test_user_ops_ui_uses_modal_import_structure(client):
    response = client.get("/admin/user-ops/ui")
    html = response.get_data(as_text=True)
    class_modal = html.split('<div id="class-term-import-modal-backdrop"', 1)[1].split(
        '<div id="activation-import-modal-backdrop"', 1
    )[0]
    activation_modal = html.split('<div id="activation-import-modal-backdrop"', 1)[1]

    assert response.status_code == 200
    assert 'id="class-term-import-modal-backdrop" class="modal-backdrop hidden"' in html
    assert 'id="activation-import-modal-backdrop" class="modal-backdrop hidden"' in html
    assert 'id="class-term-import-modal-title">导入学员（手机号 + 班期）<' in class_modal
    assert '<label for="class-term-import-text">粘贴导入</label>' in class_modal
    assert '<label for="class-term-import-file">Excel 导入</label>' in class_modal
    assert 'id="submit-class-term-import-btn"' in class_modal
    assert 'id="close-class-term-import-modal-btn"' in class_modal
    assert '>导入学员</button>' in class_modal
    assert 'id="activation-import-modal-title">导入黄小璨激活状态<' in activation_modal
    assert '<label for="activation-import-text">粘贴导入</label>' in activation_modal
    assert '<label for="activation-import-file">Excel 导入</label>' in activation_modal
    assert 'id="submit-activation-import-btn"' in activation_modal
    assert 'id="close-activation-import-modal-btn"' in activation_modal
    assert '>导入黄小璨激活状态</button>' in activation_modal
    assert "13800138040,已激活" in html


def test_sync_user_ops_class_term_tag_definitions_updates_tag_identity_fields(app, user_ops_contact_client):
    user_ops_contact_client._corp_tag_payload = _build_corp_tag_payload(
        [
            ("tag-term-1", "首期7天改变计划"),
            ("tag-term-3", "0322改变计划-第3期"),
            ("tag-term-4", "0330改变计划-第4期"),
        ],
        group_id="group-verified",
    )

    with app.app_context():
        payload = sync_user_ops_class_term_tag_definitions()

        assert payload["ok"] is True
        assert payload["synced_count"] == 3
        rows = get_db().execute(
            """
            SELECT tag_name, strategy_id, group_id, tag_id
            FROM class_term_tag_mapping
            ORDER BY class_term_no ASC
            """
        ).fetchall()
        assert rows[0]["strategy_id"] == ""
        assert rows[0]["group_id"] == "group-verified"
        assert rows[0]["tag_id"] == "tag-term-1"


def test_refresh_contact_tags_for_external_userid_writes_all_tags_when_scope_is_none(app, user_ops_contact_client):
    user_ops_contact_client.set_contact_detail(
        "wm_refresh_all_001",
        _build_external_contact_detail(
            external_userid="wm_refresh_all_001",
            owner_userid="sales_01",
            follow_user_tags=[
                {"id": "tag-all-1", "name": "全量标签1"},
                {"id": "tag-all-2", "name": "全量标签2"},
            ],
        ),
    )

    with app.app_context():
        payload = refresh_contact_tags_for_external_userid(
            external_userid="wm_refresh_all_001",
            owner_userid="sales_01",
            scoped_tag_ids=None,
        )

        assert payload["ok"] is True
        assert payload["scoped_all_tags"] is True
        rows = get_db().execute(
            """
            SELECT tag_id, tag_name
            FROM contact_tags
            WHERE external_userid = ? AND userid = ?
            ORDER BY tag_id ASC
            """,
            ("wm_refresh_all_001", "sales_01"),
        ).fetchall()
        assert [row["tag_id"] for row in rows] == ["tag-all-1", "tag-all-2"]


def test_refresh_contact_tags_for_external_userid_only_refreshes_scoped_tags(app, user_ops_contact_client):
    user_ops_contact_client.set_contact_detail(
        "wm_refresh_scope_001",
        _build_external_contact_detail(
            external_userid="wm_refresh_scope_001",
            owner_userid="sales_01",
            follow_user_tags=[
                {"id": "tag-term-1", "name": "首期7天改变计划"},
                {"id": "tag-other-9", "name": "其他标签"},
            ],
        ),
    )

    with app.app_context():
        payload = refresh_contact_tags_for_external_userid(
            external_userid="wm_refresh_scope_001",
            owner_userid="sales_01",
            scoped_tag_ids=["tag-term-1"],
        )

        assert payload["ok"] is True
        assert payload["scoped_all_tags"] is False
        rows = get_db().execute(
            """
            SELECT tag_id, tag_name
            FROM contact_tags
            WHERE external_userid = ? AND userid = ?
            ORDER BY tag_id ASC
            """,
            ("wm_refresh_scope_001", "sales_01"),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["tag_id"] == "tag-term-1"


def test_import_experience_leads_from_pasted_text_survives_reload(client, app):
    response = client.post(
        "/api/admin/user-ops/import-experience-leads",
        json={"pasted_text": "13800138009\n13800138010"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["unique_mobile_count"] == 2
    assert payload["reload"]["total"] == 2

    list_payload = client.get("/api/admin/user-ops/list").get_json()
    mobiles = {item["mobile"] for item in list_payload["items"]}
    assert {"13800138009", "13800138010"} <= mobiles

    client.post("/api/admin/user-ops/reload")
    list_payload_after_reload = client.get("/api/admin/user-ops/list").get_json()
    mobiles_after_reload = {item["mobile"] for item in list_payload_after_reload["items"]}
    assert {"13800138009", "13800138010"} <= mobiles_after_reload


def test_import_experience_leads_from_excel_visible_in_pool(client):
    response = client.post(
        "/api/admin/user-ops/import-experience-leads",
        data={"file": (BytesIO(_build_test_xlsx([["手机号"], ["13800138011"]])), "experience.xlsx")},
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["unique_mobile_count"] == 1

    list_payload = client.get("/api/admin/user-ops/list").get_json()
    assert list_payload["total"] == 1
    assert list_payload["items"][0]["mobile"] == "13800138011"


def test_import_experience_leads_deduplicates_mobile_source_rows(client, app):
    response = client.post(
        "/api/admin/user-ops/import-experience-leads",
        json={"pasted_text": "13800138012\n13800138012\n13800138012"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["duplicate_count"] == 2

    with app.app_context():
        row = get_db().execute(
            "SELECT COUNT(*) AS total FROM user_ops_experience_leads WHERE mobile = ?",
            ("13800138012",),
        ).fetchone()
        assert row["total"] == 1
        pool_count = get_db().execute(
            "SELECT COUNT(*) AS total FROM user_ops_pool_current WHERE mobile = ?",
            ("13800138012",),
        ).fetchone()
        assert pool_count["total"] == 1


def test_imported_mobile_only_user_stays_unbound_in_pool(client):
    response = client.post(
        "/api/admin/user-ops/import-experience-leads",
        json={"pasted_text": "13800138013"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True

    list_payload = client.get("/api/admin/user-ops/list?query=13800138013").get_json()
    assert list_payload["total"] == 1
    assert list_payload["items"][0]["mobile"] == "13800138013"
    assert list_payload["items"][0]["external_userid"] == ""
    assert list_payload["items"][0]["is_wecom_bound"] is False
    assert list_payload["items"][0]["current_status"] == "lead_trial"


def test_imported_mobile_matching_binding_auto_fills_crm_fields(client, app):
    _seed_user_ops_sources(app)

    response = client.post(
        "/api/admin/user-ops/import-experience-leads",
        json={"pasted_text": "13800138002"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True

    list_payload = client.get("/api/admin/user-ops/list?query=13800138002").get_json()
    assert list_payload["total"] == 1
    item = list_payload["items"][0]
    assert item["mobile"] == "13800138002"
    assert item["external_userid"] == "wm_lead_bound"
    assert item["owner_userid"] == "sales_01"
    assert item["customer_name"] == "已绑定引流用户"
    assert item["is_wecom_bound"] is True


def test_import_experience_leads_does_not_downgrade_signed_status(client, app):
    _seed_user_ops_sources(app)

    response = client.post(
        "/api/admin/user-ops/import-experience-leads",
        json={"pasted_text": "13800138000\n13800138001"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True

    list_payload = client.get("/api/admin/user-ops/list").get_json()
    by_mobile = {item["mobile"]: item for item in list_payload["items"]}
    assert by_mobile["13800138000"]["current_status"] == "signed_999"
    assert by_mobile["13800138001"]["current_status"] == "signed_3999"


def test_imported_experience_leads_survive_explicit_reload(client):
    client.post(
        "/api/admin/user-ops/import-experience-leads",
        json={"pasted_text": "13800138014"},
    )

    first_list = client.get("/api/admin/user-ops/list?query=13800138014").get_json()
    assert first_list["total"] == 1

    reload_response = client.post("/api/admin/user-ops/reload")
    assert reload_response.status_code == 200

    second_list = client.get("/api/admin/user-ops/list?query=13800138014").get_json()
    assert second_list["total"] == 1
    assert second_list["items"][0]["mobile"] == "13800138014"


def test_import_mobile_class_terms_from_pasted_text_updates_pool(client):
    response = client.post(
        "/api/admin/user-ops/import-mobile-class-terms",
        json={"pasted_text": "13800138015,5期"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["unique_mobile_count"] == 1

    list_payload = client.get("/api/admin/user-ops/list?query=13800138015").get_json()
    assert list_payload["total"] == 1
    item = list_payload["items"][0]
    assert item["mobile"] == "13800138015"
    assert item["class_term_no"] == 5
    assert item["class_term_label"] == "5期"
    assert item["external_userid"] == ""
    assert item["is_wecom_bound"] is False


def test_import_mobile_class_terms_matching_binding_marks_wecom_bound(client, app):
    _seed_user_ops_sources(app)

    response = client.post(
        "/api/admin/user-ops/import-mobile-class-terms",
        json={"pasted_text": "13800138002,6期"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["bound_count"] == 1

    list_payload = client.get("/api/admin/user-ops/list?query=13800138002").get_json()
    assert list_payload["total"] == 1
    item = list_payload["items"][0]
    assert item["mobile"] == "13800138002"
    assert item["external_userid"] == "wm_lead_bound"
    assert item["is_wecom_bound"] is True
    assert item["class_term_label"] == "6期"


def test_import_mobile_class_terms_keeps_latest_row_for_same_mobile(client):
    response = client.post(
        "/api/admin/user-ops/import-mobile-class-terms",
        data={
            "file": (
                BytesIO(_build_test_xlsx([["手机号", "班期"], ["13800138016", "5期"], ["13800138016", "6期"]])),
                "class-term.xlsx",
            )
        },
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["duplicate_count"] == 1

    before_reload = client.get("/api/admin/user-ops/list?query=13800138016").get_json()
    assert before_reload["items"][0]["class_term_label"] == "6期"

    client.post("/api/admin/user-ops/reload")

    after_reload = client.get("/api/admin/user-ops/list?query=13800138016").get_json()
    assert after_reload["items"][0]["class_term_no"] == 6
    assert after_reload["items"][0]["class_term_label"] == "6期"


def test_import_activation_status_from_pasted_text_updates_pool(client):
    response = client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138020,已激活"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True

    list_payload = client.get("/api/admin/user-ops/list?query=13800138020").get_json()
    assert list_payload["total"] == 1
    assert list_payload["items"][0]["activation_status"] == "activated"
    assert list_payload["items"][0]["activation_status_label"] == "已激活"
    assert list_payload["items"][0]["activation_remark"] == ""


def test_import_activation_status_from_excel_updates_pool(client):
    response = client.post(
        "/api/admin/user-ops/import-activation-status",
        data={
            "file": (
                BytesIO(_build_test_xlsx([["手机号", "状态"], ["13800138021", "已激活"]])),
                "activation.xlsx",
            )
        },
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True

    list_payload = client.get("/api/admin/user-ops/list?query=13800138021").get_json()
    assert list_payload["total"] == 1
    assert list_payload["items"][0]["activation_status"] == "activated"
    assert list_payload["items"][0]["activation_status_label"] == "已激活"


def test_import_activation_status_accepts_not_activated_label(client):
    response = client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138031,未激活"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True

    list_payload = client.get("/api/admin/user-ops/list?query=13800138031").get_json()
    assert list_payload["total"] == 1
    assert list_payload["items"][0]["activation_status"] == "not_activated"
    assert list_payload["items"][0]["activation_status_label"] == "未激活"


def test_import_activation_status_accepts_legacy_activated_label(client):
    response = client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138032,激活"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True

    list_payload = client.get("/api/admin/user-ops/list?query=13800138032").get_json()
    assert list_payload["total"] == 1
    assert list_payload["items"][0]["activation_status"] == "activated"
    assert list_payload["items"][0]["activation_status_label"] == "已激活"


def test_import_activation_status_rejects_invalid_value(client):
    response = client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138022,高意向"},
    )
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["error"] == "invalid activation rows: 13800138022,高意向 -> activation_status is invalid: 高意向 (allowed: 已激活, 未激活)"


def test_import_activation_status_source_keeps_latest_row(client, app):
    response = client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138023,未激活\n13800138023,激活"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["duplicate_count"] == 1

    with app.app_context():
        row = get_db().execute(
            "SELECT COUNT(*) AS total FROM user_ops_activation_status_source WHERE mobile = ?",
            ("13800138023",),
        ).fetchone()
        assert row["total"] == 1
        current = get_db().execute(
            """
            SELECT activation_status, activation_remark
            FROM user_ops_activation_status_source
            WHERE mobile = ?
            """,
            ("13800138023",),
        ).fetchone()
        assert current["activation_status"] == "activated"
        assert current["activation_remark"] == ""


def test_phone_centric_imports_keep_external_userid_binding_derived(client, app):
    _seed_user_ops_sources(app)

    class_term_response = client.post(
        "/api/admin/user-ops/import-mobile-class-terms",
        json={
            "pasted_text": "13800138002,6期",
            "external_userid": "wm_should_not_be_written",
        },
    )
    activation_response = client.post(
        "/api/admin/user-ops/import-activation-status",
        json={
            "pasted_text": "13800138002,激活",
            "external_userid": "wm_should_not_be_written",
        },
    )

    assert class_term_response.status_code == 200
    assert activation_response.status_code == 200

    list_payload = client.get("/api/admin/user-ops/list?query=13800138002").get_json()
    assert list_payload["total"] == 1
    item = list_payload["items"][0]
    assert item["mobile"] == "13800138002"
    assert item["external_userid"] == "wm_lead_bound"
    assert item["is_wecom_bound"] is True
    assert item["class_term_label"] == "6期"
    assert item["activation_status"] == "activated"


def test_phone_centric_sources_and_projection_fields_stay_split(client, app):
    client.post(
        "/api/admin/user-ops/import-mobile-class-terms",
        json={"pasted_text": "13800138061,5期"},
    )
    client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138061,未激活"},
    )
    client.post("/api/admin/user-ops/reload")

    with app.app_context():
        db = get_db()
        lead_row = db.execute(
            "SELECT mobile, source_type FROM user_ops_experience_leads WHERE mobile = ?",
            ("13800138061",),
        ).fetchone()
        activation_row = db.execute(
            "SELECT mobile, activation_status, activation_remark FROM user_ops_activation_status_source WHERE mobile = ?",
            ("13800138061",),
        ).fetchone()
        current_row = db.execute(
            """
            SELECT mobile, external_userid, is_wecom_bound, class_term_no, class_term_label, activation_status
            FROM user_ops_pool_current
            WHERE mobile = ?
            """,
            ("13800138061",),
        ).fetchone()

    assert lead_row["mobile"] == "13800138061"
    assert lead_row["source_type"] == "class_term_import"
    assert activation_row["mobile"] == "13800138061"
    assert activation_row["activation_status"] == "not_activated"
    assert activation_row["activation_remark"] == ""
    assert current_row["mobile"] == "13800138061"
    assert current_row["external_userid"] == ""
    assert bool(current_row["is_wecom_bound"]) is False
    assert current_row["class_term_no"] == 5
    assert current_row["class_term_label"] == "5期"
    assert current_row["activation_status"] == "not_activated"


def test_activation_status_survives_reload(client):
    client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138024,激活"},
    )
    before_reload = client.get("/api/admin/user-ops/list?query=13800138024").get_json()
    assert before_reload["items"][0]["activation_status"] == "activated"

    client.post("/api/admin/user-ops/reload")

    after_reload = client.get("/api/admin/user-ops/list?query=13800138024").get_json()
    assert after_reload["items"][0]["activation_status"] == "activated"


def test_activation_import_creates_mobile_only_unbound_pool_row(client):
    response = client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138025,未激活"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True

    list_payload = client.get("/api/admin/user-ops/list?query=13800138025").get_json()
    assert list_payload["total"] == 1
    item = list_payload["items"][0]
    assert item["mobile"] == "13800138025"
    assert item["external_userid"] == ""
    assert item["is_wecom_bound"] is False
    assert item["activation_status"] == "not_activated"


def test_activation_status_filter_works(client):
    client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138026,激活\n13800138027,未激活"},
    )

    activated_payload = client.get("/api/admin/user-ops/list?activation_status=activated").get_json()
    not_activated_payload = client.get("/api/admin/user-ops/list?activation_status=not_activated").get_json()

    assert {item["mobile"] for item in activated_payload["items"]} == {"13800138026"}
    assert {item["mobile"] for item in not_activated_payload["items"]} == {"13800138027"}


def test_history_contains_activation_import_upsert_records(client):
    client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138028,激活"},
    )

    history_payload = client.get("/api/admin/user-ops/history").get_json()
    activation_rows = [item for item in history_payload["items"] if item["action_type"] == "activation_import_upsert"]
    assert activation_rows
    assert activation_rows[0]["mobile"] == "13800138028"


def test_activation_import_list_shows_activated_and_not_activated(client):
    client.post(
        "/api/admin/user-ops/import-activation-status",
        json={"pasted_text": "13800138029,已激活\n13800138030,未激活"},
    )

    list_payload = client.get("/api/admin/user-ops/list").get_json()
    by_mobile = {item["mobile"]: item for item in list_payload["items"]}

    assert by_mobile["13800138029"]["activation_status"] == "activated"
    assert by_mobile["13800138029"]["activation_status_label"] == "已激活"
    assert by_mobile["13800138030"]["activation_status"] == "not_activated"
    assert by_mobile["13800138030"]["activation_status_label"] == "未激活"


def test_external_contact_event_for_zhaoyanfang_creates_deferred_auto_assign_job(app, monkeypatch):
    detail = _build_external_contact_detail(
        external_userid="wm_auto_assign_001",
        owner_userid="ZhaoYanFang",
    )
    dispatched: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr("wecom_ability_service.routes._contact_client", lambda: _FakeCallbackContactClient(detail))
    monkeypatch.setattr(
        "wecom_ability_service.routes._dispatch_background_task",
        lambda task_name, task_fn, *args, **kwargs: dispatched.append((task_name, args)),
    )

    with app.app_context():
        logged = log_external_contact_event(
            corp_id="ww-test",
            event_type="change_external_contact",
            change_type="add_external_contact",
            external_userid="wm_auto_assign_001",
            user_id="ZhaoYanFang",
            event_time=1775000000,
            event_key="event-auto-assign-001",
            payload_xml="<xml></xml>",
            payload_json={"ChangeType": "add_external_contact"},
        )
        result = _process_external_contact_event(int(logged["id"]))

        assert result["ok"] is True
        job = get_db().execute(
            """
            SELECT job_type, external_userid, owner_userid, status, run_after
            FROM user_ops_deferred_jobs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert job["job_type"] == "auto_assign_class_term"
        assert job["external_userid"] == "wm_auto_assign_001"
        assert job["owner_userid"] == "ZhaoYanFang"
        assert job["status"] == "pending"
        assert str(job["run_after"] or "").strip() != ""
        assert dispatched[0][0] == "user_ops_auto_assign_class_term"


def test_external_contact_event_for_other_owner_does_not_create_deferred_job(app, monkeypatch):
    detail = _build_external_contact_detail(
        external_userid="wm_auto_assign_002",
        owner_userid="sales_01",
    )
    monkeypatch.setattr("wecom_ability_service.routes._contact_client", lambda: _FakeCallbackContactClient(detail))
    monkeypatch.setattr("wecom_ability_service.routes._dispatch_background_task", lambda *args, **kwargs: None)

    with app.app_context():
        logged = log_external_contact_event(
            corp_id="ww-test",
            event_type="change_external_contact",
            change_type="add_external_contact",
            external_userid="wm_auto_assign_002",
            user_id="sales_01",
            event_time=1775000001,
            event_key="event-auto-assign-002",
            payload_xml="<xml></xml>",
            payload_json={"ChangeType": "add_external_contact"},
        )
        result = _process_external_contact_event(int(logged["id"]))

        assert result["ok"] is True
        row = get_db().execute(
            "SELECT COUNT(*) AS total FROM user_ops_deferred_jobs",
        ).fetchone()
        assert row["total"] == 0


def test_deferred_job_does_not_run_before_run_after(client, app):
    _seed_zhao_contact(app, external_userid="wm_auto_due_001")

    with app.app_context():
        scheduled = schedule_user_ops_auto_assign_class_term_job(
            external_userid="wm_auto_due_001",
            owner_userid="ZhaoYanFang",
            delay_seconds=10,
        )
        assert scheduled["scheduled"] is True

    response = client.post("/api/admin/user-ops/run-deferred-jobs", json={"limit": 20})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["scanned_count"] == 0

    with app.app_context():
        job = get_db().execute(
            "SELECT status FROM user_ops_deferred_jobs WHERE external_userid = ?",
            ("wm_auto_due_001",),
        ).fetchone()
        assert job["status"] == "pending"


def test_due_deferred_job_writes_class_term_for_single_match(client, app, user_ops_contact_client):
    _seed_zhao_contact(app, external_userid="wm_auto_due_002")
    user_ops_contact_client.set_contact_detail(
        "wm_auto_due_002",
        _build_external_contact_detail(
            external_userid="wm_auto_due_002",
            owner_userid="ZhaoYanFang",
            follow_user_tags=[{"id": "tag-term-1", "name": "首期7天改变计划"}],
        ),
    )

    with app.app_context():
        scheduled = schedule_user_ops_auto_assign_class_term_job(
            external_userid="wm_auto_due_002",
            owner_userid="ZhaoYanFang",
            delay_seconds=0,
        )
        assert scheduled["scheduled"] is True

    response = client.post("/api/admin/user-ops/run-deferred-jobs", json={"limit": 20})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success_count"] == 1
    with app.app_context():
        pool_row = get_db().execute(
            "SELECT class_term_no, class_term_label FROM user_ops_pool_current WHERE external_userid = ?",
            ("wm_auto_due_002",),
        ).fetchone()
        assert pool_row["class_term_no"] == 1
        assert pool_row["class_term_label"] == "1期"
        job = get_db().execute(
            "SELECT status FROM user_ops_deferred_jobs WHERE external_userid = ?",
            ("wm_auto_due_002",),
        ).fetchone()
        assert job["status"] == "success"
        history = get_db().execute(
            "SELECT action_type FROM user_ops_pool_history WHERE external_userid = ? ORDER BY id DESC LIMIT 1",
            ("wm_auto_due_002",),
        ).fetchone()
        assert history["action_type"] == "class_term_auto_assign"
        refreshed_tag = get_db().execute(
            "SELECT tag_id, tag_name FROM contact_tags WHERE external_userid = ? AND userid = ?",
            ("wm_auto_due_002", "ZhaoYanFang"),
        ).fetchone()
        assert refreshed_tag["tag_id"] == "tag-term-1"


def test_due_deferred_job_conflict_is_skipped(client, app, user_ops_contact_client):
    _seed_zhao_contact(app, external_userid="wm_auto_due_003")
    user_ops_contact_client.set_contact_detail(
        "wm_auto_due_003",
        _build_external_contact_detail(
            external_userid="wm_auto_due_003",
            owner_userid="ZhaoYanFang",
            follow_user_tags=[
                {"id": "tag-term-1", "name": "首期7天改变计划"},
                {"id": "tag-term-4", "name": "0330改变计划-第4期"},
            ],
        ),
    )

    with app.app_context():
        schedule_user_ops_auto_assign_class_term_job(
            external_userid="wm_auto_due_003",
            owner_userid="ZhaoYanFang",
            delay_seconds=0,
        )

    response = client.post("/api/admin/user-ops/run-deferred-jobs", json={"limit": 20})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["conflict_count"] == 1
    with app.app_context():
        pool_row = get_db().execute(
            "SELECT class_term_no, class_term_label FROM user_ops_pool_current WHERE external_userid = ?",
            ("wm_auto_due_003",),
        ).fetchone()
        assert pool_row["class_term_no"] in (None, "")
        assert pool_row["class_term_label"] == ""
        job = get_db().execute(
            "SELECT status FROM user_ops_deferred_jobs WHERE external_userid = ?",
            ("wm_auto_due_003",),
        ).fetchone()
        assert job["status"] == "conflict"


def test_due_deferred_job_without_match_is_skipped(client, app, user_ops_contact_client):
    _seed_zhao_contact(app, external_userid="wm_auto_due_004")
    user_ops_contact_client.set_contact_detail(
        "wm_auto_due_004",
        _build_external_contact_detail(
            external_userid="wm_auto_due_004",
            owner_userid="ZhaoYanFang",
            follow_user_tags=[],
        ),
    )

    with app.app_context():
        schedule_user_ops_auto_assign_class_term_job(
            external_userid="wm_auto_due_004",
            owner_userid="ZhaoYanFang",
            delay_seconds=0,
        )

    response = client.post("/api/admin/user-ops/run-deferred-jobs", json={"limit": 20})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["skipped_count"] == 1
    with app.app_context():
        job = get_db().execute(
            "SELECT status FROM user_ops_deferred_jobs WHERE external_userid = ?",
            ("wm_auto_due_004",),
        ).fetchone()
        assert job["status"] == "skipped"
        history = get_db().execute(
            "SELECT action_type FROM user_ops_pool_history WHERE external_userid = ? ORDER BY id DESC LIMIT 1",
            ("wm_auto_due_004",),
        ).fetchone()
        assert history["action_type"] == "class_term_auto_assign_skip"


def test_backfill_class_term_dry_run_returns_preview_without_writing(client, app, user_ops_contact_client):
    _seed_user_ops_sources(app)
    user_ops_contact_client.set_contact_detail(
        "wm_signed_999",
        _build_external_contact_detail(
            external_userid="wm_signed_999",
            owner_userid="sales_01",
            follow_user_tags=[{"id": "tag-term-1", "name": "首期7天改变计划"}],
        ),
    )
    client.post("/api/admin/user-ops/reload")

    response = client.post(
        "/api/admin/user-ops/backfill-class-term",
        json={"owner_userid": "sales_01", "dry_run": True},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["update_count"] == 1

    with app.app_context():
        row = get_db().execute(
            "SELECT class_term_no, class_term_label FROM user_ops_pool_current WHERE external_userid = ?",
            ("wm_signed_999",),
        ).fetchone()
        assert row["class_term_no"] in (None, "")
        assert row["class_term_label"] == ""
        refreshed_tag = get_db().execute(
            "SELECT tag_id FROM contact_tags WHERE external_userid = ? AND userid = ?",
            ("wm_signed_999", "sales_01"),
        ).fetchone()
        assert refreshed_tag["tag_id"] == "tag-term-1"


def test_backfill_class_term_apply_updates_pool(client, app, user_ops_contact_client):
    _seed_user_ops_sources(app)
    user_ops_contact_client.set_contact_detail(
        "wm_signed_999",
        _build_external_contact_detail(
            external_userid="wm_signed_999",
            owner_userid="sales_01",
            follow_user_tags=[],
        ),
    )
    user_ops_contact_client.set_contact_detail(
        "wm_lead_bound",
        _build_external_contact_detail(
            external_userid="wm_lead_bound",
            owner_userid="sales_01",
            follow_user_tags=[{"id": "tag-term-3", "name": "别名也能命中"}],
        ),
    )
    client.post("/api/admin/user-ops/reload")

    response = client.post(
        "/api/admin/user-ops/backfill-class-term",
        json={"owner_userid": "sales_01", "dry_run": False, "confirm": True},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["dry_run"] is False
    assert payload["applied_count"] == 1

    with app.app_context():
        row = get_db().execute(
            "SELECT class_term_no, class_term_label FROM user_ops_pool_current WHERE external_userid = ?",
            ("wm_lead_bound",),
        ).fetchone()
        assert row["class_term_no"] == 3
        assert row["class_term_label"] == "3期"


def test_backfill_class_term_conflict_is_reported_and_skipped(client, app, user_ops_contact_client):
    _seed_user_ops_sources(app)
    user_ops_contact_client.set_contact_detail(
        "wm_signed_999",
        _build_external_contact_detail(
            external_userid="wm_signed_999",
            owner_userid="sales_01",
            follow_user_tags=[
                {"id": "tag-term-1", "name": "首期7天改变计划"},
                {"id": "tag-term-4", "name": "0330改变计划-第4期"},
            ],
        ),
    )
    user_ops_contact_client.set_contact_detail(
        "wm_lead_bound",
        _build_external_contact_detail(
            external_userid="wm_lead_bound",
            owner_userid="sales_01",
            follow_user_tags=[],
        ),
    )
    client.post("/api/admin/user-ops/reload")

    dry_run_payload = client.post(
        "/api/admin/user-ops/backfill-class-term",
        json={"owner_userid": "sales_01", "dry_run": True},
    ).get_json()
    assert dry_run_payload["conflict_count"] == 1

    apply_payload = client.post(
        "/api/admin/user-ops/backfill-class-term",
        json={"owner_userid": "sales_01", "dry_run": False, "confirm": True},
    ).get_json()
    assert apply_payload["conflict_count"] == 1
    assert apply_payload["applied_count"] == 0

    with app.app_context():
        row = get_db().execute(
            "SELECT class_term_no, class_term_label FROM user_ops_pool_current WHERE external_userid = ?",
            ("wm_signed_999",),
        ).fetchone()
        assert row["class_term_no"] in (None, "")
        assert row["class_term_label"] == ""


def test_backfill_class_term_no_match_keeps_existing_value(client, app, user_ops_contact_client):
    _seed_user_ops_sources(app)
    user_ops_contact_client.set_contact_detail(
        "wm_signed_999",
        _build_external_contact_detail(
            external_userid="wm_signed_999",
            owner_userid="sales_01",
            follow_user_tags=[],
        ),
    )
    user_ops_contact_client.set_contact_detail(
        "wm_lead_bound",
        _build_external_contact_detail(
            external_userid="wm_lead_bound",
            owner_userid="sales_01",
            follow_user_tags=[],
        ),
    )
    client.post("/api/admin/user-ops/reload")
    with app.app_context():
        db = get_db()
        db.execute(
            """
            UPDATE user_ops_pool_current
            SET class_term_no = ?, class_term_label = ?, updated_at = CURRENT_TIMESTAMP
            WHERE external_userid = ?
            """,
            (4, "4期", "wm_signed_999"),
        )
        db.commit()

    response = client.post(
        "/api/admin/user-ops/backfill-class-term",
        json={"owner_userid": "sales_01", "dry_run": False, "confirm": True},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["no_match_count"] >= 1

    with app.app_context():
        row = get_db().execute(
            "SELECT class_term_no, class_term_label FROM user_ops_pool_current WHERE external_userid = ?",
            ("wm_signed_999",),
        ).fetchone()
        assert row["class_term_no"] == 4
        assert row["class_term_label"] == "4期"


def test_backfill_class_term_history_records_apply_and_conflict(client, app, user_ops_contact_client):
    _seed_user_ops_sources(app)
    user_ops_contact_client.set_contact_detail(
        "wm_lead_bound",
        _build_external_contact_detail(
            external_userid="wm_lead_bound",
            owner_userid="sales_01",
            follow_user_tags=[{"id": "tag-term-3", "name": "0322改变计划-第3期"}],
        ),
    )
    user_ops_contact_client.set_contact_detail(
        "wm_signed_999",
        _build_external_contact_detail(
            external_userid="wm_signed_999",
            owner_userid="sales_01",
            follow_user_tags=[
                {"id": "tag-term-1", "name": "首期7天改变计划"},
                {"id": "tag-term-4", "name": "0330改变计划-第4期"},
            ],
        ),
    )
    client.post("/api/admin/user-ops/reload")
    client.post(
        "/api/admin/user-ops/backfill-class-term",
        json={"owner_userid": "sales_01", "dry_run": False, "confirm": True},
    )

    history_payload = client.get("/api/admin/user-ops/history").get_json()
    action_types = {item["action_type"] for item in history_payload["items"]}
    assert "class_term_backfill_apply" in action_types
    assert "class_term_backfill_conflict" in action_types


def test_backfill_class_term_requires_confirm_for_real_write(client, app, user_ops_contact_client):
    _seed_user_ops_sources(app)
    user_ops_contact_client.set_contact_detail(
        "wm_signed_999",
        _build_external_contact_detail(
            external_userid="wm_signed_999",
            owner_userid="sales_01",
            follow_user_tags=[],
        ),
    )
    user_ops_contact_client.set_contact_detail(
        "wm_lead_bound",
        _build_external_contact_detail(
            external_userid="wm_lead_bound",
            owner_userid="sales_01",
            follow_user_tags=[{"id": "tag-term-3", "name": "0322改变计划-第3期"}],
        ),
    )
    client.post("/api/admin/user-ops/reload")

    response = client.post(
        "/api/admin/user-ops/backfill-class-term",
        json={"owner_userid": "sales_01", "dry_run": False},
    )
    payload = response.get_json()

    assert response.status_code == 400
    assert payload == {"ok": False, "error": "confirm_required"}

    with app.app_context():
        row = get_db().execute(
            "SELECT class_term_no, class_term_label FROM user_ops_pool_current WHERE external_userid = ?",
            ("wm_lead_bound",),
        ).fetchone()
        assert row["class_term_no"] in (None, "")
        assert row["class_term_label"] == ""


def test_backfill_class_term_rejects_confirm_false_for_real_write(client, app, user_ops_contact_client):
    _seed_user_ops_sources(app)
    user_ops_contact_client.set_contact_detail(
        "wm_signed_999",
        _build_external_contact_detail(
            external_userid="wm_signed_999",
            owner_userid="sales_01",
            follow_user_tags=[],
        ),
    )
    user_ops_contact_client.set_contact_detail(
        "wm_lead_bound",
        _build_external_contact_detail(
            external_userid="wm_lead_bound",
            owner_userid="sales_01",
            follow_user_tags=[{"id": "tag-term-3", "name": "0322改变计划-第3期"}],
        ),
    )
    client.post("/api/admin/user-ops/reload")

    response = client.post(
        "/api/admin/user-ops/backfill-class-term",
        json={"owner_userid": "sales_01", "dry_run": False, "confirm": False},
    )
    payload = response.get_json()

    assert response.status_code == 400
    assert payload == {"ok": False, "error": "confirm_required"}

    with app.app_context():
        row = get_db().execute(
            "SELECT class_term_no, class_term_label FROM user_ops_pool_current WHERE external_userid = ?",
            ("wm_lead_bound",),
        ).fetchone()
        assert row["class_term_no"] in (None, "")
        assert row["class_term_label"] == ""
