from __future__ import annotations

from wecom_ability_service.domains.user_ops.page_service import (
    _index_manual_dnd_rows,
    _manual_dnd_reasons_for_identity,
)


def test_manual_dnd_reason_lookup_uses_identity_indexes_and_dedupes_reasons():
    rows = [
        {
            "external_userid": "wm_001",
            "mobile": "",
            "source_type": "manual",
            "reason_code": "manual_set",
            "reason_text": "运营设置",
        },
        {
            "external_userid": "",
            "mobile": "13800138000",
            "source_type": "manual",
            "reason_code": "manual_set",
            "reason_text": "运营设置",
        },
        {
            "external_userid": "",
            "mobile": "13800138000",
            "source_type": "auto",
            "reason_code": "signed_paid_course",
            "reason_text": "已报名正价课",
        },
        {
            "external_userid": "wm_other",
            "mobile": "13900139000",
            "source_type": "manual",
            "reason_code": "manual_set",
            "reason_text": "无关客户",
        },
    ]
    rows_by_external, rows_by_mobile = _index_manual_dnd_rows(rows)

    reasons = _manual_dnd_reasons_for_identity(
        external_userid="wm_001",
        mobile="13800138000",
        rows_by_external=rows_by_external,
        rows_by_mobile=rows_by_mobile,
    )

    assert reasons == [
        {"source_type": "manual", "reason_code": "manual_set", "reason_text": "运营设置"},
        {"source_type": "auto", "reason_code": "signed_paid_course", "reason_text": "已报名正价课"},
    ]
