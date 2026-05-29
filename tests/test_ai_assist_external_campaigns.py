from __future__ import annotations

import inspect

import pytest
from fastapi.testclient import TestClient

from aicrm_next.ai_assist import external_campaigns
from aicrm_next.main import create_app
from wecom_ability_service.domains.campaigns import service as campaign_service
from wecom_ability_service.domains.segments import service as segment_service


def _db():
    from wecom_ability_service.db import get_db

    return get_db()


def _seed_contact(external_userid: str, owner_userid: str = "HuangYouCan") -> None:
    db = _db()
    db.execute(
        """
        INSERT INTO contacts (external_userid, owner_userid, customer_name, remark)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (external_userid) DO UPDATE SET owner_userid = excluded.owner_userid
        """,
        (external_userid, owner_userid, f"name-{external_userid}", f"remark-{external_userid}"),
    )
    db.commit()


def _seed_pool_current(external_userid: str, owner_userid: str = "HuangYouCan", row_id: int = 900001) -> None:
    db = _db()
    db.execute(
        """
        INSERT INTO user_ops_pool_current
            (id, mobile, external_userid, customer_name, owner_userid,
             current_status, is_wecom_bound, activation_status, source_type)
        VALUES (?, ?, ?, ?, ?, 'active_focus', ?, 'activated', 'test')
        ON CONFLICT (id) DO UPDATE SET
            external_userid = excluded.external_userid,
            owner_userid = excluded.owner_userid
        """,
        (row_id, f"138{row_id % 100000000:08d}"[-11:], external_userid, f"name-{external_userid}", owner_userid, True),
    )
    db.commit()


def _seed_automation_member(external_userid: str, owner_userid: str = "HuangYouCan", row_id: int = 910001) -> None:
    db = _db()
    db.execute(
        """
        INSERT INTO automation_member
            (id, external_contact_id, owner_staff_id, in_pool, current_pool,
             current_audience_code, source_type)
        VALUES (?, ?, ?, ?, 'operating', 'operating', 'test')
        ON CONFLICT (id) DO UPDATE SET
            external_contact_id = excluded.external_contact_id,
            owner_staff_id = excluded.owner_staff_id
        """,
        (row_id, external_userid, owner_userid, True),
    )
    db.commit()


def test_external_campaign_create_requires_internal_token(monkeypatch) -> None:
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "internal-token")
    client = TestClient(create_app())

    response = client.post(
        "/api/ai-assist/external/campaigns",
        json={
            "owner_userid": "HuangYouCan",
            "external_userid": "external-1",
            "scheduled_for": "2026-05-28 16:15",
            "message": "咱今天还报名吗？",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"] == "missing_internal_token"


def test_external_campaign_create_route_invokes_creator_after_auth(monkeypatch) -> None:
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "internal-token")
    captured = {}

    def fake_create(payload):
        captured["payload"] = payload
        return {
            "ok": True,
            "route_owner": "ai_crm_next",
            "created_count": 1,
            "existing_count": 0,
            "campaigns": [{"campaign_code": "camp_ext_test", "status": "created"}],
        }

    monkeypatch.setattr(external_campaigns, "create_external_campaigns", fake_create)
    client = TestClient(create_app())

    response = client.post(
        "/api/ai-assist/external/campaigns",
        headers={"Authorization": "Bearer internal-token"},
        json={
            "owner_userid": "HuangYouCan",
            "external_userid": "external-1",
            "scheduled_for": "2026-05-28 16:15",
            "message": "咱今天还报名吗？",
        },
    )

    assert response.status_code == 200
    assert response.json()["created_count"] == 1
    assert captured["payload"]["owner_userid"] == "HuangYouCan"


def test_external_campaign_status_requires_internal_token(monkeypatch) -> None:
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "internal-token")
    client = TestClient(create_app())

    response = client.get("/api/ai-assist/external/campaigns/camp_ext_test")

    assert response.status_code == 401
    assert response.json()["error"] == "missing_internal_token"


def test_external_campaign_status_route_invokes_reader_after_auth(monkeypatch) -> None:
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "internal-token")
    captured = {}

    def fake_get(campaign_code):
        captured["campaign_code"] = campaign_code
        return {
            "ok": True,
            "route_owner": "ai_crm_next",
            "campaign": {"campaign_code": campaign_code},
            "total_members": 1,
            "scheduled_jobs": 1,
        }

    monkeypatch.setattr(external_campaigns, "get_external_campaign_status", fake_get)
    client = TestClient(create_app())

    response = client.get(
        "/api/ai-assist/external/campaigns/camp_ext_test",
        headers={"Authorization": "Bearer internal-token"},
    )

    assert response.status_code == 200
    assert response.json()["campaign"]["campaign_code"] == "camp_ext_test"
    assert captured["campaign_code"] == "camp_ext_test"


def test_external_campaign_normalizes_multi_day_steps() -> None:
    steps = external_campaigns._normalize_step_list(
        [
            {"scheduled_for": "2026-05-28 16:15", "content_text": "D0"},
            {"day_offset": 1, "send_time": "10:30", "content_text": "D1"},
        ],
        {},
        {"external_userid": "external-1"},
        timezone_name="Asia/Shanghai",
    )

    assert steps[0]["day_offset"] == 0
    assert steps[0]["send_time"] == "16:15"
    assert steps[0]["scheduled_for"] == "2026-05-28T16:15:00+08:00"
    assert steps[1]["day_offset"] == 1
    assert steps[1]["send_time"] == "10:30"


def test_external_campaign_segment_sql_uses_synthetic_member_id() -> None:
    sql = external_campaigns._ONE_RECIPIENT_SEGMENT_SQL

    assert "hashtext(external_userid)" in sql
    assert "hashtext(external_contact_id)" in sql
    assert "SELECT id AS member_id" not in sql
    assert "external_contact_id" in sql


def test_campaign_segment_params_accept_pg_jsonb_dict() -> None:
    params = {"external_userid": "wm-test"}

    assert campaign_service._json_object(params) == params
    assert segment_service._json_object(params) == params
    assert campaign_service._json_object('{"external_userid":"wm-test"}') == params
    assert segment_service._json_object('{"external_userid":"wm-test"}') == params


def test_external_campaign_create_stops_before_start() -> None:
    source = inspect.getsource(external_campaigns._create_single_recipient_campaign)

    assert "submit_campaign_for_review" in source
    assert "issue_token" not in source
    assert "start_campaign" not in source
    assert "requires_human_review" in source


def test_lookup_target_resolves_user_ops_pool_current_without_automation_member(app) -> None:
    with app.app_context():
        _seed_pool_current("wm-pool-only", row_id=920001)

        target = external_campaigns._lookup_target(
            external_userid="wm-pool-only",
            owner_userid="HuangYouCan",
            strict_owner_match=True,
        )

        assert target["source"] == "user_ops_pool_current"
        assert target["pool_current"]["external_userid"] == "wm-pool-only"
        assert target["member"] == {}


def test_lookup_target_resolves_automation_member_without_user_ops_pool_current(app) -> None:
    with app.app_context():
        _seed_automation_member("wm-member-only", row_id=920002)

        target = external_campaigns._lookup_target(
            external_userid="wm-member-only",
            owner_userid="HuangYouCan",
            strict_owner_match=True,
        )

        assert target["source"] == "automation_member"
        assert target["member"]["external_contact_id"] == "wm-member-only"


def test_lookup_target_owner_mismatch_uses_contacts_owner(app) -> None:
    with app.app_context():
        _seed_pool_current("wm-owner-mismatch", row_id=920003)
        _seed_contact("wm-owner-mismatch", owner_userid="OtherOwner")

        with pytest.raises(external_campaigns.ExternalCampaignError) as excinfo:
            external_campaigns._lookup_target(
                external_userid="wm-owner-mismatch",
                owner_userid="HuangYouCan",
                strict_owner_match=True,
            )

        assert excinfo.value.status_code == 409
        assert excinfo.value.error == "owner_mismatch"
        assert str(excinfo.value) == "owner_mismatch:contact_owner=OtherOwner:requested_owner=HuangYouCan"


def test_lookup_target_contact_query_failure_does_not_block_pool_match(app, monkeypatch) -> None:
    with app.app_context():
        _seed_pool_current("wm-contact-query-fails", row_id=920004)

        def raise_contact_error(cur, external_userid):
            raise RuntimeError("contacts unavailable")

        monkeypatch.setattr(external_campaigns, "_fetch_contact_row", raise_contact_error)

        target = external_campaigns._lookup_target(
            external_userid="wm-contact-query-fails",
            owner_userid="HuangYouCan",
            strict_owner_match=True,
        )

        assert target["source"] == "user_ops_pool_current"
        assert target["contact"] == {}


def test_lookup_target_missing_pool_and_member_returns_target_not_found(app) -> None:
    with app.app_context():
        _seed_contact("wm-contact-only", owner_userid="HuangYouCan")

        with pytest.raises(external_campaigns.ExternalCampaignError) as excinfo:
            external_campaigns._lookup_target(
                external_userid="wm-contact-only",
                owner_userid="HuangYouCan",
                strict_owner_match=True,
            )

        assert excinfo.value.status_code == 404
        assert excinfo.value.error == "target_not_found"
        assert str(excinfo.value) == "target_not_found:wm-contact-only"


def test_backfill_automation_members_dry_run_would_insert_without_write(app) -> None:
    with app.app_context():
        _seed_contact("wm-backfill-dry-run", owner_userid="HuangYouCan")

        result = external_campaigns.backfill_automation_members_for_external_campaign(
            owner_userid="HuangYouCan",
            external_userids=["wm-backfill-dry-run"],
            operator="pytest",
            dry_run=True,
        )

        assert result["would_insert_count"] == 1
        assert result["results"][0]["status"] == "would_insert"
        row = _db().execute(
            "SELECT id FROM automation_member WHERE external_contact_id = ?",
            ("wm-backfill-dry-run",),
        ).fetchone()
        assert row is None


def test_backfill_automation_members_real_insert_creates_member(app) -> None:
    with app.app_context():
        _seed_contact("wm-backfill-real", owner_userid="HuangYouCan")

        result = external_campaigns.backfill_automation_members_for_external_campaign(
            owner_userid="HuangYouCan",
            external_userids=["wm-backfill-real"],
            operator="pytest",
            dry_run=False,
        )

        assert result["inserted_count"] == 1
        row = _db().execute(
            """
            SELECT external_contact_id, owner_staff_id, in_pool, current_pool,
                   current_audience_code, source_type
            FROM automation_member
            WHERE external_contact_id = ?
            """,
            ("wm-backfill-real",),
        ).fetchone()
        assert dict(row) == {
            "external_contact_id": "wm-backfill-real",
            "owner_staff_id": "HuangYouCan",
            "in_pool": True,
            "current_pool": "operating",
            "current_audience_code": "operating",
            "source_type": "external_campaign_backfill",
        }


def test_create_external_campaigns_auto_backfills_contact_only_target(app) -> None:
    with app.app_context():
        _seed_contact("wm-auto-backfill-create", owner_userid="HuangYouCan")

        result = external_campaigns.create_external_campaigns(
            {
                "owner_userid": "HuangYouCan",
                "external_userid": "wm-auto-backfill-create",
                "scheduled_for": "2099-01-01 10:00",
                "timezone": "Asia/Shanghai",
                "message": "hello",
                "idempotency_key": "auto-backfill-create",
                "group_code": "auto-backfill-create",
                "group_label": "auto backfill create",
                "intent": "test auto backfill create",
                "auto_backfill_automation_member": True,
            }
        )

        assert result["created_count"] == 1, result
        assert result["backfill_summary"]["inserted_count"] == 1
        assert result["campaigns"][0]["review_status"] == "pending_review"
        assert result["campaigns"][0]["run_status"] == "draft"


def test_create_external_campaigns_auto_backfill_skips_owner_mismatch(app) -> None:
    with app.app_context():
        _seed_contact("wm-auto-backfill-good", owner_userid="HuangYouCan")
        _seed_contact("wm-auto-backfill-mismatch", owner_userid="OtherOwner")

        result = external_campaigns.create_external_campaigns(
            {
                "owner_userid": "HuangYouCan",
                "recipients": [
                    {"external_userid": "wm-auto-backfill-good", "message": "good"},
                    {"external_userid": "wm-auto-backfill-mismatch", "message": "bad"},
                ],
                "scheduled_for": "2099-01-01 10:00",
                "timezone": "Asia/Shanghai",
                "idempotency_key": "auto-backfill-skip",
                "group_code": "auto-backfill-skip",
                "group_label": "auto backfill skip",
                "intent": "test auto backfill skip",
                "auto_backfill_automation_member": True,
            }
        )

        assert result["created_count"] == 1, result
        assert result["resolved_count"] == 1
        assert result["skipped_count"] == 1
        assert result["owner_mismatch_count"] == 1
        assert result["skipped_recipients"][0]["external_userid"] == "wm-auto-backfill-mismatch"
        assert result["skipped_recipients"][0]["status"] == "owner_mismatch"


def test_external_campaign_allocation_zero_deletes_half_created_campaign(app, monkeypatch) -> None:
    with app.app_context():
        _seed_automation_member("wm-allocation-zero", row_id=920005)
        _seed_contact("wm-allocation-zero", owner_userid="HuangYouCan")

        monkeypatch.setattr(
            campaign_service,
            "allocate_campaign_members",
            lambda *, campaign_id: {
                "campaign_id": campaign_id,
                "allocated": 0,
                "errors": [{"reason": "forced zero"}],
            },
        )

        with pytest.raises(external_campaigns.ExternalCampaignError) as excinfo:
            external_campaigns.create_external_campaigns(
                {
                    "owner_userid": "HuangYouCan",
                    "external_userid": "wm-allocation-zero",
                    "scheduled_for": "2099-01-01 10:00",
                    "timezone": "Asia/Shanghai",
                    "message": "hello",
                    "idempotency_key": "allocation-zero-cleanup",
                    "group_code": "allocation-zero-cleanup",
                    "group_label": "allocation zero cleanup",
                    "intent": "test allocation cleanup",
                }
            )

        assert excinfo.value.error == "campaign_member_allocation_failed"
        assert excinfo.value.phase == "allocation"
        assert excinfo.value.details["cleanup_ok"] is True
        row = _db().execute(
            "SELECT id FROM campaigns WHERE campaign_code = ?",
            (excinfo.value.campaign_code,),
        ).fetchone()
        assert row is None
