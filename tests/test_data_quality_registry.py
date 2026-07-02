from __future__ import annotations

from aicrm_next.data_health.quality_registry import (
    data_quality_checks_by_group,
    get_data_quality_check_definition,
    list_data_quality_check_definitions,
    list_data_quality_groups,
)


EXPECTED_GROUP_COUNTS = {
    "identity": 5,
    "payment": 4,
    "questionnaire": 4,
    "delivery": 4,
    "customer_projection": 3,
}


def test_data_quality_registry_groups_all_operational_rules() -> None:
    groups = list_data_quality_groups()
    checks = list_data_quality_check_definitions()
    grouped = data_quality_checks_by_group()

    assert [group["group"] for group in groups] == list(EXPECTED_GROUP_COUNTS)
    assert {group: len(items) for group, items in grouped.items()} == EXPECTED_GROUP_COUNTS
    assert len(checks) == sum(EXPECTED_GROUP_COUNTS.values())
    assert len({check["check_id"] for check in checks}) == len(checks)


def test_data_quality_registry_contains_phase7_contract_ids() -> None:
    check_ids = {check["check_id"] for check in list_data_quality_check_definitions()}

    assert {
        "identity_pending_queue_threshold",
        "identity_conflict_count",
        "identity_unionid_duplicate",
        "identity_external_userid_multi_unionid",
        "identity_mobile_multi_active_unionid",
        "payment_paid_order_missing_identity",
        "payment_paid_order_missing_product_code",
        "payment_refund_amount_exceeds_paid",
        "payment_provider_status_inconsistent",
        "questionnaire_submission_missing_unionid",
        "questionnaire_submission_missing_answers",
        "questionnaire_answer_missing_question",
        "questionnaire_final_tags_malformed",
        "delivery_broadcast_job_blocked",
        "delivery_external_effect_retryable_failures",
        "delivery_outbound_task_failed",
        "delivery_stuck_queued_claimed",
        "customer_projection_read_model_stale",
        "customer_projection_customer_360_stale",
        "customer_projection_timeline_missing_recent_activity",
    } == check_ids


def test_data_quality_registry_is_metadata_only_until_probes_are_attached() -> None:
    checks = list_data_quality_check_definitions()

    assert {check["probe_status"] for check in checks} == {"needs_probe"}
    assert {check["severity"] for check in checks} <= {"red", "yellow"}
    for check in checks:
        assert check["title"]
        assert check["description"]
        assert check["signal"]
        assert check["threshold"]
        assert check["source_tables"]
        assert check["remediation"]


def test_data_quality_registry_keeps_identity_values_out_of_payloads() -> None:
    serialized = str(list_data_quality_check_definitions())

    for forbidden in (
        "external_userid_value",
        "openid_value",
        "mobile_normalized_value",
        "unionid_value",
        "raw_payload_json",
    ):
        assert forbidden not in serialized


def test_data_quality_registry_lookup_returns_single_definition() -> None:
    definition = get_data_quality_check_definition("delivery_stuck_queued_claimed")

    assert definition is not None
    assert definition["group"] == "delivery"
    assert definition["source_tables"] == [
        "broadcast_jobs",
        "external_effect_job",
        "outbound_tasks",
    ]
    assert get_data_quality_check_definition("not_a_quality_check") is None
