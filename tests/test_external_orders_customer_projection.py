from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from aicrm_next.customer_read_model.backfill import CustomerReadModelBackfillService
from aicrm_next.customer_read_model.repo import FixtureCustomerReadRepository, LiveSourceCustomerReadRepository


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    session = sessionmaker(bind=engine, future=True)()
    for ddl in [
        """
        CREATE TABLE contacts (
            external_userid TEXT, owner_userid TEXT, customer_name TEXT,
            remark TEXT, description TEXT, updated_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE external_contact_bindings (
            external_userid TEXT, last_owner_userid TEXT, first_owner_userid TEXT,
            person_id TEXT, updated_at TIMESTAMP
        )
        """,
        "CREATE TABLE people (id TEXT, mobile TEXT, third_party_user_id TEXT)",
        """
        CREATE TABLE wecom_external_contact_identity_map (
            id INTEGER, external_userid TEXT, unionid TEXT, openid TEXT,
            follow_user_userid TEXT, name TEXT, status TEXT, updated_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE wecom_external_contact_follow_users (
            id INTEGER, external_userid TEXT, user_id TEXT, relation_status TEXT,
            is_primary BOOLEAN, remark TEXT, description TEXT, updated_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE automation_channel_contact (
            id INTEGER, channel_id INTEGER, external_contact_id TEXT,
            owner_staff_id TEXT, source_payload_json TEXT, updated_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE wechat_pay_orders (
            id INTEGER, external_userid TEXT, status TEXT, trade_state TEXT,
            order_source TEXT, paid_at TIMESTAMP, updated_at TIMESTAMP, created_at TIMESTAMP
        )
        """,
        "CREATE TABLE contact_tags (external_userid TEXT, tag_name TEXT, tag_id TEXT)",
        """
        CREATE TABLE class_user_status_current (
            external_userid TEXT, owner_userid_snapshot TEXT, customer_name_snapshot TEXT,
            mobile_snapshot TEXT, signup_status TEXT, signup_label_name TEXT,
            status_flags_json TEXT, updated_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE archived_messages (
            id INTEGER, msgid TEXT, chat_type TEXT, external_userid TEXT,
            owner_userid TEXT, sender TEXT, receiver TEXT, msgtype TEXT,
            content TEXT, send_time TIMESTAMP, raw_payload TEXT, created_at TIMESTAMP
        )
        """,
        "CREATE TABLE owner_role_map (userid TEXT, display_name TEXT)",
    ]:
        session.execute(text(ddl))
    return session


def _empty_target() -> FixtureCustomerReadRepository:
    target = FixtureCustomerReadRepository()
    target.replace_all(customers=[], timeline_by_external_userid={}, messages_by_external_userid={})
    return target


def _insert_paid_h5_order_with_channel_contact(session, *, external_userid: str = "wm_projection_001") -> None:
    now = datetime(2026, 6, 22, tzinfo=timezone.utc)
    session.execute(
        text(
            """
            INSERT INTO wechat_pay_orders (
                id, external_userid, status, trade_state, order_source, paid_at, updated_at, created_at
            )
            VALUES (156, :external_userid, 'paid', 'SUCCESS', 'h5_checkout', :now, :now, :now)
            """
        ),
        {"external_userid": external_userid, "now": now},
    )
    session.execute(
        text(
            """
            INSERT INTO automation_channel_contact (
                id, channel_id, external_contact_id, owner_staff_id, source_payload_json, updated_at
            )
            VALUES (
                1, 77, :external_userid, 'owner_channel_a',
                '{"customer_name":"H5 Paid Customer","remark":"paid via h5 checkout"}',
                :now
            )
            """
        ),
        {"external_userid": external_userid, "now": now},
    )
    session.commit()


def test_h5_checkout_paid_order_can_resolve_customer_projection_source() -> None:
    session = _session()
    _insert_paid_h5_order_with_channel_contact(session)
    repo = LiveSourceCustomerReadRepository(session)

    customer = repo.get_customer("wm_projection_001")

    assert customer is not None
    assert customer["external_userid"] == "wm_projection_001"
    assert customer["owner_userid"] == "owner_channel_a"
    assert customer["customer_name"] == "H5 Paid Customer"
    assert customer["remark"] == "paid via h5 checkout"
    assert customer["sidebar_context"]["customer_profile_url"] == "/admin/customers/wm_projection_001"


def test_channel_contact_linkage_can_feed_customer_read_model_projection() -> None:
    session = _session()
    _insert_paid_h5_order_with_channel_contact(session)
    source = LiveSourceCustomerReadRepository(session)
    target = _empty_target()

    result = CustomerReadModelBackfillService(source=source, target_repo=target).run(
        dry_run=False,
        external_userids=["wm_projection_001"],
    )

    projected = target.get_customer("wm_projection_001")
    assert result.written_customers == 1
    assert projected is not None
    assert projected["owner_userid"] == "owner_channel_a"
    assert projected["customer_name"] == "H5 Paid Customer"


def test_external_order_projection_source_missing_identity_stays_absent() -> None:
    session = _session()
    now = datetime(2026, 6, 22, tzinfo=timezone.utc)
    session.execute(
        text(
            """
            INSERT INTO wechat_pay_orders (
                id, external_userid, status, trade_state, order_source, paid_at, updated_at, created_at
            )
            VALUES (157, '', 'paid', 'SUCCESS', 'h5_checkout', :now, :now, :now)
            """
        ),
        {"now": now},
    )
    session.commit()
    repo = LiveSourceCustomerReadRepository(session)

    assert repo.get_customer("") is None
    assert repo.count_customers({}) == 0
