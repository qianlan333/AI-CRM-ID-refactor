from __future__ import annotations

from wecom_ability_service.domains.automation_conversion import service as automation_conversion_service
from wecom_ability_service.domains.marketing_automation import presenter as marketing_presenter
from wecom_ability_service.domains.marketing_automation import service as marketing_service


def test_shared_state_defs_freeze_public_values():
    assert marketing_service.POOL_NEW_USER == "new_user"
    assert marketing_service.POOL_INACTIVE_NORMAL == "inactive_normal"
    assert marketing_service.POOL_INACTIVE_FOCUS == "inactive_focus"
    assert marketing_service.POOL_ACTIVE_NORMAL == "active_normal"
    assert marketing_service.POOL_ACTIVE_FOCUS == "active_focus"
    assert marketing_service.POOL_SILENT == "silent"
    assert marketing_service.FOLLOWUP_SEGMENT_UNKNOWN == "unknown"
    assert marketing_service.FOLLOWUP_SEGMENT_NORMAL == "normal"
    assert marketing_service.FOLLOWUP_SEGMENT_FOCUS == "focus"
    assert automation_conversion_service.POOL_NEW_USER == "new_user"
    assert automation_conversion_service.POOL_INACTIVE_NORMAL == "inactive_normal"
    assert automation_conversion_service.POOL_INACTIVE_FOCUS == "inactive_focus"
    assert automation_conversion_service.POOL_ACTIVE_NORMAL == "active_normal"
    assert automation_conversion_service.POOL_ACTIVE_FOCUS == "active_focus"
    assert automation_conversion_service.POOL_SILENT == "silent"
    assert marketing_service._FOCUS_POOL_KEYS == {"inactive_focus", "active_focus"}
    assert automation_conversion_service.FOCUS_SEND_ALLOWED_POOLS == {"inactive_focus", "active_focus"}
    assert marketing_service._FOLLOWUP_SEGMENT_LABELS["unknown"] == "未完成初判"
    assert marketing_service._FOLLOWUP_SEGMENT_LABELS["focus"] == "重点跟进"
    assert marketing_service._POOL_LABELS["new_user"] == "新用户池"
    assert marketing_service._POOL_LABELS["active_focus"] == "激活重点跟进池"
    assert automation_conversion_service.POOL_LABELS["new_user"] == "新用户池"
    assert automation_conversion_service.POOL_LABELS["active_focus"] == "激活重点跟进池"


def test_shared_label_renderer_freezes_exact_cn_strings():
    assert marketing_presenter.business_stage_label(stage_key="pool/active_focus") == "激活重点跟进池"
    assert marketing_presenter.business_stage_label(stage_key="converted/enrolled") == "已确认成交"
    assert marketing_presenter.business_segment_label("unknown") == "未完成初判"
    assert marketing_presenter.business_segment_label("core") == "重点跟进"
    assert marketing_presenter.business_eligibility_label(True) == "会"
    assert marketing_presenter.business_eligibility_label(False) == "不会"
    assert marketing_presenter.business_ineligible_reason(
        reason="trial_not_opened",
        main_stage="pool",
        sub_stage="new_user",
        eligible_for_conversion=False,
    ) == "问卷已提交，等待开通试用后再进入对应池子。"
