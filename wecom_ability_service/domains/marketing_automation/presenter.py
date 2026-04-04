from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def marketing_stage_key(*, main_stage: Any = "", sub_stage: Any = "", stage_key: Any = "") -> str:
    normalized_stage_key = _text(stage_key)
    if normalized_stage_key:
        return normalized_stage_key
    normalized_main_stage = _text(main_stage)
    normalized_sub_stage = _text(sub_stage)
    if normalized_main_stage and normalized_sub_stage:
        return f"{normalized_main_stage}/{normalized_sub_stage}"
    return normalized_main_stage or normalized_sub_stage


def business_stage_label(*, main_stage: Any = "", sub_stage: Any = "", stage_key: Any = "") -> str:
    normalized_stage_key = marketing_stage_key(main_stage=main_stage, sub_stage=sub_stage, stage_key=stage_key)
    return {
        "prospect/mobile_only": "待转化",
        "prospect/wecom_connected": "待转化",
        "active/activated": "已开始使用",
        "converted/enrolled": "已报名成功",
    }.get(normalized_stage_key, "暂无阶段")


def business_segment_label(segment: Any) -> str:
    normalized_segment = _text(segment).lower()
    return {
        "unknown": "暂未分层",
        "normal": "普通用户",
        "core": "重点用户",
        "top": "最高优先用户",
    }.get(normalized_segment, "暂未分层")


def business_eligibility_label(eligible_for_conversion: Any) -> str:
    return "会" if bool(eligible_for_conversion) else "不会"


def business_ineligible_reason(
    *,
    reason: Any = "",
    main_stage: Any = "",
    sub_stage: Any = "",
    eligible_for_conversion: Any = False,
) -> str:
    if bool(eligible_for_conversion):
        return ""
    normalized_reason = _text(reason)
    stage = marketing_stage_key(main_stage=main_stage, sub_stage=sub_stage)
    mapping = {
        "enrolled": "客户已报名成功，已退出自动化。",
        "signup_success": "客户已报名成功，已退出自动化。",
        "missing_external_userid": "客户还没建立企微联系，暂时不会进入自动化。",
        "mobile_only": "客户还没建立企微联系，暂时不会进入自动化。",
        "stage_not_conversion_target": "客户当前阶段暂时不会进入自动化。",
        "segment_not_core_top": "客户当前优先级还没进入自动化范围。",
        "not_eligible": "客户当前暂时不会进入自动化。",
    }
    if normalized_reason in mapping:
        return mapping[normalized_reason]
    if stage == "converted/enrolled":
        return mapping["enrolled"]
    if stage == "prospect/mobile_only":
        return mapping["missing_external_userid"]
    return normalized_reason or mapping["not_eligible"]


def business_marketing_display(
    *,
    main_stage: Any = "",
    sub_stage: Any = "",
    segment: Any = "",
    eligible_for_conversion: Any = False,
    ineligible_reason: Any = "",
) -> dict[str, str]:
    return {
        "stage_label": business_stage_label(main_stage=main_stage, sub_stage=sub_stage),
        "segment_label": business_segment_label(segment),
        "eligibility_label": business_eligibility_label(eligible_for_conversion),
        "ineligible_reason_label": business_ineligible_reason(
            reason=ineligible_reason,
            main_stage=main_stage,
            sub_stage=sub_stage,
            eligible_for_conversion=eligible_for_conversion,
        ),
    }


def marketing_state_change_summary(*, previous_stage: Any = "", current_stage: Any = "") -> str:
    previous_label = business_stage_label(stage_key=previous_stage)
    current_label = business_stage_label(stage_key=current_stage)
    if previous_stage and previous_stage != current_stage:
        return f"客户阶段从{previous_label}变为{current_label}"
    if current_stage:
        return f"客户阶段更新为{current_label}"
    return "客户阶段已更新"


def value_segment_change_summary(*, previous_segment: Any = "", current_segment: Any = "") -> str:
    previous_label = business_segment_label(previous_segment)
    current_label = business_segment_label(current_segment)
    if previous_segment and previous_segment != current_segment:
        return f"客户分层从{previous_label}变为{current_label}"
    if current_segment:
        return f"客户分层更新为{current_label}"
    return "客户分层已更新"


def conversion_marked_summary(action: Any, source: Any) -> str:
    normalized_action = _text(action)
    normalized_source = _text(source)
    source_prefix = "人工" if normalized_source.startswith("sidebar") or normalized_source == "manual" or not normalized_source else "系统"
    if normalized_action == "mark_enrolled":
        return f"{source_prefix}确认客户已报名成功，自动化已停止。"
    if normalized_action == "unmark_enrolled":
        return f"{source_prefix}撤销报名成功标记，系统已重新判断客户阶段。"
    return "报名状态已更新。"
