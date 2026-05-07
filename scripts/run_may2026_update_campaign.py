"""5 月版本更新群发计划 — 一键准备分层 + Campaign 草稿。

人群定位：
- 范围：默认自动化转化方案（signup_conversion_v1）下、运营中的成员
- 筛选：年收入低于 100 万 + 表达过私教需求

执行流程：
1. 自动从 questionnaires + submission_answers 找"年收入"题和"私教"题（fuzzy 匹配）
2. 列出该题的所有选项让运营确认（避免误选）
3. 生成 segment SQL，调 propose_segment 创建命名分层
4. 调 propose_campaign 创建多步运营计划草稿（默认 3 步节奏）
5. 提交 review，等运营在 CRM 后台 /admin/cloud-orchestrator/campaigns 启动

用法（在服务器上跑）：
    cd '/home/ubuntu/极简 crm'
    source /home/ubuntu/venvs/openclaw/bin/activate
    set -a; source /home/ubuntu/.openclaw-wecom-pg.env; set +a

    # 第 1 步：诊断模式 — 看自动找到的题/选项是否正确
    python3 scripts/run_may2026_update_campaign.py --diagnose

    # 第 2 步：确认参数后真创建（dry-run 不真创建，仅打印计划）
    python3 scripts/run_may2026_update_campaign.py --dry-run

    # 第 3 步：真创建（不会真发，只是写入 draft Campaign，CRM 后台审阅启动才真发）
    python3 scripts/run_may2026_update_campaign.py --commit
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


CAMPAIGN_NAME = "5 月新版本激活 · 百万以下需私教用户"
SEGMENT_CODE = "income_lt_100w_with_coach_intent"
SEGMENT_DISPLAY_NAME = "百万以下 + 需私教 · 5月版本激活目标"
SEGMENT_DESCRIPTION = (
    "默认自动化转化方案下、运营中的成员，问卷答过年收入 < 100 万 + 表达过私教需求；"
    "5 月新版本（个人成长地图 + 功课 + 私教模式）的核心激活对象。"
)


# 5 个产品更新点 — 用户原文（保持原意 + 简化为话术友好的句式）
UPDATE_HIGHLIGHTS = [
    "个人成长地图 + 功课系统正式上线",
    "强化「个人商业私教模式」+「个人核心课题」，围绕你的核心问题定制专属功课",
    "意图识别更准了，无关误带入显著减少",
    "首页聊天支持「轻松问答」+「深度教练咨询」两种模式，可同时挂多个教练",
    "底层数据架构已为后续几版迭代提前重构",
]


# 多步话术 — Day 0 / Day 3 / Day 7 三步节奏
STEP_CONTENTS = [
    # Day 0 — 上新通知 + 立即可用
    (
        "Hi～新版本上线了，给你提一下最相关的两件事：\n"
        "1）个人成长地图 + 功课系统：根据你之前的咨询，老黄会按 10 分钟给你界定核心课题，"
        "再派几个具体功课跟着做\n"
        "2）「个人商业私教模式」强化了：可以围绕你正在卡的那一件事持续修正调整\n"
        "你之前的所有聊天记录、测评、咨询都完整保留。打开小程序就能继续。"
    ),
    # Day 3 — 没回应的话讲价值 + 给一个轻入口
    (
        "上次说的新版本，最值得试的是「核心课题界定」这个动作 —— "
        "10 分钟把你当前真正卡住的问题敲下来，比泛泛聊有效得多。"
        "如果最近忙没时间深聊，先「随便看看」也行，进去先扫一眼成长地图。"
    ),
    # Day 7 — 最后机会 / 行动闭环
    (
        "想让你试一次「界定核心课题 + 派功课」的私教闭环 —— "
        "对照你的实际业务节点（比如百万以下阶段的精准获客 / 转化闭环），10 分钟就能跑出第一份功课清单。"
        "本周内打开小程序点「界定我的核心课题」就行。"
    ),
]


def _ensure_app():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from wecom_ability_service import create_app

    return create_app()


def discover_questions_and_options(*, db) -> dict[str, Any]:
    """模糊找'年收入'题和'私教'题，列出选项给运营确认。"""
    cur = db.cursor()
    out: dict[str, Any] = {"income": [], "coach": []}
    for keyword, slot in (("收入", "income"), ("私教", "coach")):
        cur.execute(
            """
            SELECT q.id AS question_id, q.title AS question_title,
                   q.questionnaire_id, qn.title AS questionnaire_title
            FROM questionnaire_questions q
            JOIN questionnaires qn ON qn.id = q.questionnaire_id
            WHERE q.title LIKE ?
            ORDER BY q.questionnaire_id DESC, q.id ASC
            """,
            (f"%{keyword}%",),
        )
        questions = [dict(r) for r in (cur.fetchall() or [])]
        for q in questions:
            cur.execute(
                """
                SELECT id AS option_id, label AS option_text
                FROM questionnaire_options
                WHERE question_id = ?
                ORDER BY sort_order ASC, id ASC
                """,
                (int(q["question_id"]),),
            )
            q["options"] = [dict(r) for r in (cur.fetchall() or [])]
        out[slot] = questions
    return out


def _print_diagnose(found: dict[str, Any]) -> None:
    print("=" * 72)
    print("第 1 步：诊断 — 检查自动找到的题/选项是否正确")
    print("=" * 72)
    for slot_label, slot_key, hint in (
        ("年收入题", "income", "应该选'低于 100 万'对应选项"),
        ("私教需求题", "coach", "应该选'需要 / 想要 / 已购买私教'相关选项"),
    ):
        print(f"\n【{slot_label}】 {hint}")
        for q in found[slot_key]:
            print(f"  问卷: {q['questionnaire_title']} (id={q['questionnaire_id']})")
            print(f"  题目: {q['question_title']} (question_id={q['question_id']})")
            for opt in q["options"]:
                print(f"    └ 选项[{opt['option_id']}] {opt['option_text']}")


def build_segment_sql(*, income_match_keywords: list[str], coach_match_keywords: list[str]) -> str:
    """生成 segment SQL — 用 LIKE 模糊匹配选项文本。"""
    income_or = " OR ".join(
        [f"qa1.selected_option_texts_snapshot LIKE '%{k}%'" for k in income_match_keywords]
    ) or "1=0"
    coach_or = " OR ".join(
        [f"qa2.selected_option_texts_snapshot LIKE '%{k}%'" for k in coach_match_keywords]
    ) or "1=0"
    return (
        "SELECT m.id AS member_id, m.external_contact_id "
        "FROM automation_member m "
        "WHERE m.current_audience_code = 'operating' "
        "  AND EXISTS (SELECT 1 FROM questionnaire_submissions qs1 "
        "              JOIN questionnaire_submission_answers qa1 ON qa1.submission_id = qs1.id "
        "              JOIN questionnaire_questions qq1 ON qq1.id = qa1.question_id "
        "              WHERE qs1.external_userid = m.external_contact_id "
        "                AND qq1.title LIKE '%收入%' "
        f"                AND ({income_or})) "
        "  AND EXISTS (SELECT 1 FROM questionnaire_submissions qs2 "
        "              JOIN questionnaire_submission_answers qa2 ON qa2.submission_id = qs2.id "
        "              JOIN questionnaire_questions qq2 ON qq2.id = qa2.question_id "
        "              WHERE qs2.external_userid = m.external_contact_id "
        "                AND qq2.title LIKE '%私教%' "
        f"                AND ({coach_or}))"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnose", action="store_true", help="只看自动找到的问卷题/选项")
    parser.add_argument("--dry-run", action="store_true", help="打印将创建的 segment + campaign，不真写库")
    parser.add_argument("--commit", action="store_true", help="真创建 segment + campaign 草稿（仍需 CRM 审阅启动才真发）")
    parser.add_argument("--income-keywords", nargs="+", default=["100万以下", "50万", "30万", "10万", "20万", "百万以下", "无"],
                        help="收入选项的匹配关键词（OR）— 默认覆盖常见 < 100w 选项")
    parser.add_argument("--coach-keywords", nargs="+", default=["需要", "想", "私教", "购买", "感兴趣", "了解"],
                        help="私教需求选项的匹配关键词（OR）")
    args = parser.parse_args()

    if not (args.diagnose or args.dry_run or args.commit):
        parser.print_help()
        sys.exit(1)

    app = _ensure_app()
    with app.app_context():
        from wecom_ability_service.db import get_db

        db = get_db()
        found = discover_questions_and_options(db=db)
        _print_diagnose(found)

        if args.diagnose:
            return

        sql = build_segment_sql(
            income_match_keywords=args.income_keywords,
            coach_match_keywords=args.coach_keywords,
        )
        print("\n" + "=" * 72)
        print("第 2 步：生成的 segment SQL")
        print("=" * 72)
        print(sql)

        # 试跑看候选数
        from wecom_ability_service.domains.segments.sql_sandbox import run_segment_query

        try:
            preview = run_segment_query(sql=sql, params={})
            print(f"\n试跑：候选 {preview['row_count']} 人，elapsed {preview['elapsed_ms']} ms")
            print("样例:", json.dumps(preview["rows"][:5], ensure_ascii=False, indent=2))
        except Exception as exc:
            print(f"试跑失败: {exc}")
            return

        # 准备 campaign 三步节奏
        steps = [
            {
                "step_index": i,
                "day_offset": [0, 3, 7][i],
                "send_time": "10:00",
                "content_text": STEP_CONTENTS[i],
                "stop_on_reply": True,
            }
            for i in range(3)
        ]
        print("\n" + "=" * 72)
        print("第 3 步：将创建的 Campaign")
        print("=" * 72)
        print(f"  名称: {CAMPAIGN_NAME}")
        print(f"  目标分层 segment_code: {SEGMENT_CODE}")
        print(f"  锚点: 成员加入 Campaign 那天 = Day 0 (member_joined_at)")
        for s in steps:
            print(f"  D+{s['day_offset']:>2} @ {s['send_time']}  {s['content_text'][:60]}…")

        if args.dry_run:
            print("\n--dry-run 模式，未真写。加 --commit 真创建草稿。")
            return

        # 真创建
        from wecom_ability_service.domains.segments.service import (
            create_segment, get_segment,
        )
        from wecom_ability_service.domains.campaigns.service import propose_campaign

        existing = get_segment(segment_code=SEGMENT_CODE)
        if existing:
            print(f"\n[skip] segment '{SEGMENT_CODE}' 已存在 id={existing['id']} headcount={existing.get('cached_headcount')}")
        else:
            seg = create_segment(
                segment_code=SEGMENT_CODE,
                display_name=SEGMENT_DISPLAY_NAME,
                description=SEGMENT_DESCRIPTION,
                sql_query=sql,
                source_type="ai_generated",
                tags=["campaign", "may2026_update"],
                operator="may2026_launch_script",
                activate=True,
            )
            print(f"\n[ok] segment 已创建 id={seg['id']} headcount={seg.get('cached_headcount')}")

        overview = propose_campaign(
            display_name=CAMPAIGN_NAME,
            intent="向百万以下 + 需私教用户介绍 5 月新版本（成长地图 + 功课 + 私教模式）",
            segments=[
                {
                    "segment_code": SEGMENT_CODE,
                    "priority": 999,
                    "label": "百万以下需私教",
                    "steps": steps,
                }
            ],
            anchor_mode="member_joined_at",
            owner_userid="",
            operator="may2026_launch_script",
            auto_allocate=True,
        )
        camp = overview["campaign"]
        print(f"\n[ok] Campaign 已创建 code={camp['campaign_code']} id={camp['id']}")
        print(f"     候选分配: {overview['allocation']['allocated']} 人")
        print(f"     状态: review={camp['review_status']} run={camp['run_status']}")
        print(
            "\n下一步：到 CRM 后台 /admin/cloud-orchestrator/campaigns 找到这个 Campaign，"
            "审阅候选 + 节奏 + 话术后点'签发 token + 启动 Campaign'即可。"
        )


if __name__ == "__main__":
    main()
