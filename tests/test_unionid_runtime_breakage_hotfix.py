from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _function_source(source: str, name: str) -> str:
    matches = list(re.finditer(rf"^(?:def|    def) {re.escape(name)}\(", source, re.MULTILINE))
    assert matches, f"missing function {name}"
    match = matches[-1]
    tail = source[match.start() :]
    next_match = re.search(r"\n(?:def|class|    def) ", tail[len(match.group(0)) :])
    return tail if not next_match else tail[: len(match.group(0)) + next_match.start()]


def test_h5_wechat_pay_notify_after_unionid_cleanup() -> None:
    source = _read("aicrm_next/public_product/h5_wechat_pay.py")
    paid_order_source = _function_source(source, "_paid_order_for_product_identity")
    apply_transaction_source = _function_source(source, "_apply_transaction")

    assert "AND unionid = %s" in paid_order_source
    assert "payer_openid" not in paid_order_source
    assert "external_userid = %s" not in paid_order_source
    assert "payer_openid" not in apply_transaction_source
    assert "notify_payload_json = %s::jsonb" in apply_transaction_source


def test_questionnaire_admin_reads_after_unionid_cleanup() -> None:
    source = _read("aicrm_next/questionnaire/repo.py")
    for name in ["list_submissions", "list_external_submissions", "find_submission_for_identity"]:
        section = _function_source(source, name)
        assert "LEFT JOIN crm_user_identity identity ON identity.unionid = qs.unionid" in section
        assert "qs.external_userid" not in section
        assert "qs.mobile_snapshot" not in section
    assert "identity.primary_external_userid" in source
    assert "identity.mobile" in source


def test_alipay_admin_transactions_after_unionid_cleanup() -> None:
    source = _read("aicrm_next/commerce/admin_transaction_detail.py")
    filter_source = _function_source(source, "_postgres_filter_clause")
    select_source = _function_source(source, "_postgres_order_select")

    assert "_identity_lookup_exists_sql" in filter_source
    assert "crm_user_identity identity" in source
    assert "where.append(\"1 = 0\")" not in filter_source
    for forbidden in ["o.mobile_snapshot", "o.identity_snapshot", "o.buyer_id", "o.userid_snapshot", "o.external_userid", "o.respondent_key"]:
        assert forbidden not in filter_source
        assert forbidden not in select_source


def test_group_ops_dispatcher_writes_target_unionids() -> None:
    source = _read("aicrm_next/automation_engine/group_ops/action_dispatcher.py")
    insert_source = _function_source(source, "_insert_broadcast_job")
    enqueue_source = _function_source(source, "enqueue_private_message")

    assert "target_unionids_json" in insert_source
    assert "'unionid'" in insert_source
    assert "target_external_userids" not in insert_source
    assert "\"unionids\"" in enqueue_source
    assert "\"external_userid\"" not in enqueue_source


def test_cloud_broadcast_plan_dispatch_uses_unionid() -> None:
    source = _read("aicrm_next/cloud_orchestrator/repository.py")
    section = source.split("def create_or_reuse_recipient_broadcast_jobs", 1)[1].split("def create_or_reuse_plan_broadcast_job", 1)[0]

    assert "SELECT id, unionid, display_name, owner_userid" in section
    assert "COALESCE(unionid, '') <> ''" in section
    assert "target_unionids_json" in section
    assert "SELECT id, external_userid" not in section
    assert "COALESCE(external_userid, '') <> ''" not in section


def test_channel_assignment_event_writes_unionid() -> None:
    source = _read("aicrm_next/channel_entry/repo.py")
    insert_source = _function_source(source, "insert_assignment_event")
    serializer_source = _function_source(source, "_serialize_assignment_event")

    assert "unionid, wecom_user_id, source_payload_json" in insert_source
    assert "_resolve_unionid_by_external_userid" in insert_source
    assert "external_contact_id, wecom_user_id" not in insert_source
    assert '"unionid": text(row.get("unionid"))' in serializer_source


def test_customer_external_userid_lookup_exact_jsonb_membership() -> None:
    source = _read("aicrm_next/customer_read_model/repo.py")
    section = _function_source(source, "_identity_by_external_userid")

    assert "jsonb_exists(external_userids_json, :external_userid)" in section
    assert "jsonb_array_elements(external_userids_json)" in section
    assert "CAST(external_userids_json AS TEXT) LIKE" not in section
    assert "external_userid_like" not in section


def test_automation_agent_webhook_item_upsert_matches_partial_index() -> None:
    source = _read("aicrm_next/automation_agents/repository.py")
    assert "ON CONFLICT (batch_id, unionid) WHERE unionid <> '' DO UPDATE" in source


def test_unionid_runtime_sql_guard_blocks_removed_identity_columns() -> None:
    h5_source = _read("aicrm_next/public_product/h5_wechat_pay.py")
    questionnaire_source = _read("aicrm_next/questionnaire/repo.py")
    commerce_source = _read("aicrm_next/commerce/admin_transaction_detail.py")
    group_ops_source = _read("aicrm_next/automation_engine/group_ops/action_dispatcher.py")
    cloud_source = _read("aicrm_next/cloud_orchestrator/repository.py")
    channel_source = _read("aicrm_next/channel_entry/repo.py")
    scoped_sources = {
        "h5_wechat_pay_runtime": (
            _function_source(h5_source, "_paid_order_for_product_identity")
            + _function_source(h5_source, "_apply_transaction"),
            [
            "payer_openid",
            "respondent_key = %s",
            "external_userid = %s",
            "userid_snapshot",
            "mobile_snapshot = %s",
            ],
        ),
        "questionnaire_admin_reads": (
            _function_source(questionnaire_source, "list_submissions")
            + _function_source(questionnaire_source, "list_external_submissions")
            + _function_source(questionnaire_source, "find_submission_for_identity"),
            [
            "qs.external_userid",
            "qs.mobile_snapshot",
            "qs.openid",
            "qs.respondent_key",
            ],
        ),
        "commerce_admin_transactions": (
            _function_source(commerce_source, "_postgres_filter_clause")
            + _function_source(commerce_source, "_postgres_order_select"),
            [
            "o.mobile_snapshot",
            "o.identity_snapshot",
            "o.buyer_id",
            "o.userid_snapshot",
            "o.external_userid",
            "o.respondent_key",
            ],
        ),
        "group_ops_broadcast_job": (
            _function_source(group_ops_source, "_insert_broadcast_job"),
            [
            "target_external_userids",
            "'external_userid', '{}'::jsonb",
            ],
        ),
        "cloud_broadcast_planner": (
            cloud_source.split("def create_or_reuse_recipient_broadcast_jobs", 1)[1].split("def create_or_reuse_plan_broadcast_job", 1)[0],
            [
            "SELECT id, external_userid, display_name, owner_userid",
            "COALESCE(external_userid, '') <> ''",
            ],
        ),
        "channel_assignment_event": (
            _function_source(channel_source, "insert_assignment_event"),
            [
            "external_contact_id, wecom_user_id, source_payload_json",
            ],
        ),
        "customer_exact_external_lookup": (
            _function_source(_read("aicrm_next/customer_read_model/repo.py"), "_identity_by_external_userid"),
            [
            "CAST(external_userids_json AS TEXT) LIKE",
            ],
        ),
        "automation_agent_webhook_item_upsert": (
            _read("aicrm_next/automation_agents/repository.py"),
            [
            "ON CONFLICT (batch_id, unionid) DO UPDATE",
            ],
        ),
    }
    for label, (source, forbidden_tokens) in scoped_sources.items():
        for token in forbidden_tokens:
            assert token not in source, f"{label} still contains runtime SQL token: {token}"
