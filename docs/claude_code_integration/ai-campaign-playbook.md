# AI 驱动 Campaign 运营 — 可复用 Playbook

> **谁该读**：任何 Claude / 其他 Agent 帮黄小璨 AI CRM 做"按某条件挑一群人，按节奏推送，运营 1 次确认"这类任务时直接看这个文档操作。
>
> **本 Playbook 解决三件事**：
> 1. **CRM 端能力地图** — 系统暴露什么 API / MCP tool 给你用
> 2. **Agent 6 步标准工作流** — 从"运营提需求"到"草稿待审"的完整路径
> 3. **写话术能力** — 怎么生成 D+0 / D+1 等节奏文案

下面每段都给可执行的命令 / curl / SQL，不留坑。

---

## 1. CRM 端能力地图

CRM 是数据 + 执行底座。你（Agent）只读 CRM 数据 + 提交草稿，**真发送必须人工在 admin 点启动**（强制 approval_token 约束）。

### 1.1 你能调的 MCP tool（外部 Agent 通道）

入口：`POST https://openclaw.youcangogogo.com/mcp`
鉴权：Bearer token（运营提供，类似 `ycgogo_ai_internal_v1_...`）
协议：JSON-RPC 2.0，`method: "tools/call"`，`params: {name, arguments}`

| Tool | 类型 | 用途 |
|---|---|---|
| `list_segments` | read | 列已有人群分层 |
| `get_segment` | read | 拿某个分层定义（含 SQL） |
| `preview_segment_members` | read | 实时跑 SQL 看候选 + 样本 |
| `list_questionnaires` | read | 列问卷（找 id） |
| `inspect_questionnaire` | read | 看题目 / 选项分布 |
| `preview_questionnaire_population` | read | 给一组 (题, 选项 ids) 预览人数 |
| `compose_segment_sql_from_questionnaire` | read | 生成跨题筛选 SQL |
| `validate_segment_sql` | read | 沙箱跑 SQL 验证不会炸 |
| `propose_segment` | **write**（无副作用） | 把一个 SQL 落库成分层（status=active） |
| `propose_campaign` | **write**（无副作用） | 一次性把 segments + steps 落成 draft Campaign + 互斥分配人选 |
| `query_recent_audit_logs` | read | 出错时查 cloud_agent_audit_log 拿 traceback |
| `query_table_schema` | read | 写 SQL 前确认列名/类型 |

**关键约束**：`propose_segment` 和 `propose_campaign` 是 draft 态的"草稿"——会落库但不会真触发推送。**真触发推送必须运营在 `/admin/cloud-orchestrator/campaigns` 里手动启动**（人工签发 approval_token + 启动按钮）。

### 1.2 SSH 直查能力（生产数据校验）

如果运营已配 SSH 受限通道（v2 sandbox：`crm-prod` host），你可以：

```bash
# 跑只读 SQL（默认 default_transaction_read_only=on，UPDATE 会被 PG 拒）
ssh crm-prod psql "SELECT count(*) FROM questionnaire_submissions WHERE questionnaire_id=21;"

# 看服务日志找 traceback
ssh crm-prod logs openclaw-wecom-postgres 200

# 看 cron 日志（campaign 调度健康）
ssh crm-prod 'tail /home/ubuntu/logs/campaign-run-due.log 30'
```

具体能力清单见运营给的私钥分发文档。

### 1.3 admin UI（运营操作 + 你给链接）

| 路径 | 用途 |
|---|---|
| `/admin/cloud-orchestrator/campaigns` | 运营审阅 + 启动 + 编辑节奏 |
| `/admin/cloud-orchestrator/observability` | 调用日志 / 错误率 / Tool 统计 |
| `/admin/image-library` | 图片素材库（上传 / 外链） |
| `/admin/miniprogram-library` | 小程序卡片素材库 |
| `/admin/customers/<external_userid>` | 单个客户详情（campaign 命中成员明细 deep-link 这里） |

### 1.4 实际推送链路（你不直接调，但要懂）

```
propose_campaign（你）
  ↓
  落库 campaigns(draft) + campaign_segments + campaign_steps + 互斥分配 campaign_members
  ↓
人工在 admin 点启动（必须）
  ↓
  campaigns.run_status = active + 计算每人 next_due_at（基于 anchor_mode）
  ↓
cron 每 15 分钟扫 next_due_at <= now 的 pending member
  ↓
process_due_campaign_members
  ↓
按 (segment_id, step_index) 分组聚合 → 1 次 dispatch_wecom_task → 企微 1 个 task 含 N 人
  ↓
运营登企微「客户群发」点 1 次确认 → 客户收到
  ↓
推进 next_due_at 到 D+N 等下一轮
```

**两条停止机制**（`stop_on_reply` step 字段控制）：
- 同步：scheduler 发下一 step 之前查 archived_messages，命中 inbound 就停
- 异步：reply_monitor cron 扫 archive 增量时也会标 replied

---

## 2. Agent 6 步标准工作流

任何"挑某类人 → 编排节奏 → 待审"任务都按这 6 步。每步给可直接复用的 MCP 调用模板。

### 步骤 1: 理解需求 + 找数据源

运营来一个需求，比如 "5 月新版本激活，针对年收入<100W 且有业务卡点的人，2 天连发"。

先识别**人群口径来源**：
- 来源 A：现成的 segment（pool / profile / behavior 维度，已经在 segments 表里）
- 来源 B：问卷答案（用户做过的问卷）
- 来源 C：自定义 SQL 组合（多种条件交集）

```json
// MCP call: list_segments
{"name": "list_segments", "arguments": {"keyword": "百万", "limit": 20}}
```

如果是问卷来的：

```json
// MCP call: list_questionnaires（按标题 grep）
{"name": "list_questionnaires", "arguments": {"keyword": "激活"}}
```

### 步骤 2: Inspect — 看题目 + 选项分布 / 看现有分层定义

问卷场景：

```json
// MCP call: inspect_questionnaire
{"name": "inspect_questionnaire", "arguments": {"questionnaire_id": 21}}
```

返回每题的 option_id / 文案 / 当前命中人数分布，让你对比运营要求确定 option ids。

现有 segment 场景：

```json
{"name": "get_segment", "arguments": {"segment_code": "active_focus_msg_lt_2"}}
```

### 步骤 3: Preview 候选人数

确认目标人群规模合理（不能超 1000，太大要拆分；不能 0，得调宽条件）。

```json
// 问卷场景：组合多题筛选预览
{"name": "preview_questionnaire_population", "arguments": {
  "questionnaire_id": 21,
  "filters": [
    {"question_id": 148, "option_ids": [384, 385, 386, 387, 388, 389]},
    {"question_id": 151, "option_ids": [401, 402, 403, 404, 405]}
  ]
}}
```

返回 `headcount` + `sample`（前 N 人 external_userid）。

### 步骤 4: Compose Segment SQL

```json
{"name": "compose_segment_sql_from_questionnaire", "arguments": {
  "questionnaire_id": 21,
  "filters": [...],
  "segment_code": "income_lt_100w_with_biz_pain_may2026",
  "display_name": "百万以下 + 有业务卡点 · 5月新版本激活目标",
  "description": "默认转化方案运营中的成员，问卷答过年收入<100万 + Q151 业务卡点（5 类）"
}}
```

返回 `sql_query` + `sql_params_json`，下一步直接传给 propose_segment。

可选：`validate_segment_sql` 拿到生成 SQL 后再跑一次确保不报错。

### 步骤 5: Propose Segment（落库 draft 分层）

```json
{"name": "propose_segment", "arguments": {
  "segment_code": "income_lt_100w_with_biz_pain_may2026",
  "display_name": "百万以下 + 有业务卡点 · 5月新版本激活目标",
  "description": "...",
  "sql_query": "<上一步返回的>",
  "sql_params_json": "{}",
  "activate": true
}}
```

返回 `segment_id` + `cached_headcount`。**这一步不发任何消息，只落分层定义**。

### 步骤 6: Propose Campaign（最终一步，落 draft Campaign + 分配人选）

把 segment + steps 一起提交，campaign 落 draft 态等运营审。**关键字段**：

```json
{"name": "propose_campaign", "arguments": {
  "display_name": "5 月新版本激活 · 百万以下需私教",
  "intent": "<完整意图描述，包含 5 月版本能力点 + 触达对象 + 引导目标>",
  "anchor_mode": "campaign_start_date",  // 或 member_joined_at
  "segments": [{
    "segment_code": "income_lt_100w_with_biz_pain_may2026",
    "priority": 999,
    "label": "百万以下 + 业务卡点",
    "steps": [
      {
        "step_index": 0,
        "day_offset": 0,
        "send_time": "10:00",
        "stop_on_reply": true,
        "content_text": "<D+0 文案>"
      },
      {
        "step_index": 1,
        "day_offset": 1,
        "send_time": "10:00",
        "stop_on_reply": true,
        "content_text": "<D+1 文案>"
      }
    ]
  }]
}}
```

返回 `campaign_code` + `trace_id` + `allocated`（实际命中人数）+ `total_members`。

**`anchor_mode` 选择**：
- `campaign_start_date` ← 推荐。D+0 锚定"启动当日 10:00"，避免 catch-up 集中推
- `member_joined_at` ← 用户加入日 + N。如果加入日比启动日早，D+0 已过期会立刻 catch-up（可能凌晨集中产生 task）

**告诉运营**：去 `/admin/cloud-orchestrator/campaigns` 找 `<campaign_code>`，审阅文案后点「启动」。trace_id 用来出错排查。

---

## 3. 写话术能力（D+0 / D+1 等节奏文案）

### 3.1 必须知道的产品边界

- **企微"客户群发" task 是待确认机制**：你提交的 content_text 进运营企微「客户群发」列表，员工点 1 次「发送」才推到客户。所以 batch dispatch 后的"重复风险"是 0（运营不点就不发）
- **D+0 / D+1 是同一个用户连续触达**：D+0 给信息密集型概览（介绍 = 三件事告诉你），D+1 给场景化深化（用法）
- **个性化变量目前不支持**：content_text 是固定文本，N 人收到一样的内容。如果要 per-member 个性化，要走 automation_workflow 链路（不是 campaign）

### 3.2 文案模板（验证过有效）

#### D+0 — 概览告知（80-150 字）

```
嗨～<品牌> 5月版本正式上线。三件事告诉你：
① 「<功能 A>」<一句话价值>；
② 强化【<功能 B 名>】+【<功能 C 名>】，<一句话价值>；
③ <交互改造，比如双模式>。打开就能用，回头一起看看～
```

要点：
- 数字 ① ② ③ 让重点一眼看完
- 「」用全角直引号包功能名（视觉抓手）
- 末尾 "回头一起看看～" 给软引导，不强求回复

#### D+1 — 场景化深化（150-220 字）

```
接昨天的版本更新～对你来说最值钱的 <数> 个用法：
① <用户痛点 → 用功能 X 怎么解>；
② <场景 → 功能 Y>；
③ <轻量入口，给不想深用的留一个>。
<可选：技术改进 1 句>。先用哪个？回我一句～
```

要点：
- 开头 "接昨天的版本更新～" 提示连续性
- "对你来说最值钱的" 隐式个性化（其实是聚合，但话术让用户感觉被针对）
- 末尾 "先用哪个？回我一句～" 直接提示回复 → 触发 stop_on_reply 停后续

### 3.3 拼装步骤

写 D+0/D+1 之前要做的功课（拿到这些素材再写）：

1. **本期版本 5 大点**：从产品/运营那要"功能更新清单"，按重要性排序
2. **目标人群的具体痛点**：通过 questionnaire 题目文案逆推（比如 Q151 = "业务定位/启动/流量/交付/增长"，文案直接 echo 这 5 个词让人产生"这就是说我"的感觉）
3. **品牌口吻**：看历史 campaign / 自动化欢迎语，模仿语气（黄小璨 = 教练私聊感，不能像产品发布会）

### 3.4 字数 / 格式 / 禁忌

- **总字数 ≤ 4000**（campaign_steps.content_text 截断阈值）
- **不要 markdown** — 企微私聊渲染纯文本，`**bold**` 会显示成字面 `**`
- **不要 \\n\\n 多空行** — 企微对消息合并空行可能丢失
- **emoji ≤ 3 个**，过多触发用户警惕（"群发感"）
- **不发链接**（除非是企微小程序卡片走 attachments）— 运营要的是回复对话，不是点击外跳

### 3.5 配图（可选）

如果要带图：

1. 先在 `/admin/image-library` 上传图片（5MB 内，自动入库）
2. 运营在 admin step 编辑表单选图（picker 多选最多 9 张），保存
3. 发送时 scheduler 自动 resolve 成企微 media_id，跟文案一起进 task

你（Agent）一般不直接传图，让运营在 UI 上选。如果运营给你图片素材库 id 了，propose_campaign 的 step 里可以传 `image_library_ids: [N]`（但 propose_campaign tool schema 当前不暴露这个字段，需走 update_step 的 PATCH endpoint）。

---

## 4. 完整端到端示例（5 月新版本激活）

### 任务

> 给"默认自动化转化方案"运营中的、年收入<100 万、且 Q151 业务卡点（5 类）的用户做 5 月新版本激活 Campaign。2 天连发：D+0 版本能力告知，D+1 场景细节。

### 6 步执行

```bash
# 1. 找问卷
curl -X POST $MCP_URL -H "Authorization: Bearer $TOKEN" -d '{
  "jsonrpc":"2.0","id":1,"method":"tools/call",
  "params":{"name":"list_questionnaires","arguments":{"keyword":"激活"}}
}'
# → questionnaire_id=21

# 2. 看题目分布
... inspect_questionnaire {"questionnaire_id": 21}
# → Q148 (年收入) 选项 [384..389]; Q151 (业务卡点) [401..405]

# 3. 预览人数
... preview_questionnaire_population {"questionnaire_id":21,"filters":[
  {"question_id":148,"option_ids":[384,385,386,387,388,389]},
  {"question_id":151,"option_ids":[401,402,403,404,405]}
]}
# → headcount=66

# 4. Compose SQL
... compose_segment_sql_from_questionnaire {同上 + segment_code,display_name}
# → sql_query

# 5. Propose Segment
... propose_segment {上面 SQL + activate=true}
# → segment_id=26, cached_headcount=66

# 6. Propose Campaign（D+0 + D+1 文案见上一节模板）
... propose_campaign {
  display_name: "5 月新版本激活 · 百万以下需私教",
  anchor_mode: "campaign_start_date",
  segments: [{segment_code:"income_lt_100w_with_biz_pain_may2026", priority:999, steps:[D+0, D+1]}]
}
# → campaign_code=camp-d12ca96a7a58, allocated=66
```

### 给运营的交付话术

> Campaign 已落草稿：`camp-d12ca96a7a58`，命中 66 人，2 天 D+0/D+1 节奏。
> 进 `/admin/cloud-orchestrator/campaigns` 审阅文案 → 点启动 → 等启动当日 10:00 cron 自动产生企微「客户群发」待确认任务（1 个含 66 人）→ 你企微点 1 次确认 → 客户收到。

---

## 5. 常见错误 + 故障排查

| 现象 | 真因 | 怎么处理 |
|---|---|---|
| `propose_segment` 返回 `headcount=0` | SQL 写错了 / 条件太严 | 用 `validate_segment_sql` 单独跑 SQL；或回到 `preview_questionnaire_population` 缩条件 |
| `propose_campaign` 返回 `allocated=0` | 互斥分配 — 这些 member 已被同 campaign 别的高优先级 segment 抢走 | 检查同 campaign 其他 segment 的 priority 是否过高 |
| 启动按钮 500 | PG 兼容 bug（历史已修 6 个） | `query_recent_audit_logs` 看 traceback；新发现的提 PR 修 + 加测试到 `tests/integration/test_pg_compat_smoke.py` |
| 启动后客户没收到 | cron 没触发 / 运营没在企微点确认 | SSH 看 `tail /home/ubuntu/logs/campaign-run-due.log`；提醒运营企微「客户群发」点确认 |
| 64 个独立 task 而不是 1 个含 64 人 | scheduler 不是 batch 模式（PR #206 已修） | 看部署版本是否 ≥ commit f43bf2f |

详细 PG 兼容性回归列表：`tests/integration/test_pg_compat_smoke.py`，每个 test 关联具体 PR。

---

## 6. 给后续 Agent 的硬规矩

1. **真发送只能人工启动** — 你产出的最末端是 draft Campaign，把 campaign_code 给运营，让 ta 在 admin 点启动
2. **anchor_mode 默认 campaign_start_date**，除非运营明确要求"按用户加入日"
3. **stop_on_reply 默认 true**，除非运营明确要求"无视回复继续推"
4. **D+0 和 D+1 之间至少留 24 小时**（day_offset >= 1），同一天连发会被企微判骚扰
5. **每条 step.content_text 控制 ≤ 220 字**，超长用 step 拆分
6. **propose_campaign 之后必须给运营 trace_id**，出问题能用它 SSH SQL `WHERE trace_id=...` 一查到底
7. **不要直接调 SQL 改数据**（你只读 / 调 MCP write tool；改写靠 admin UI 或运营手动）
8. **同一 segment_code 可以反复 propose_segment**（idempotent，update 同条），但运营常用"语义化命名 + 日期后缀"避免冲突，比如 `income_lt_100w_with_biz_pain_may2026`

---

## 7. 历史 Reference

- 6 个 PG 兼容 bug 全景：`tests/integration/test_pg_compat_smoke.py`
- 调度引擎设计：`wecom_ability_service/domains/campaigns/scheduler.py` 文件头注释
- 互斥分配算法：`wecom_ability_service/domains/campaigns/service.py:allocate_campaign_members`
- 图片/小程序素材库：`docs/development/pg-integration-tests.md` + 各 domain `__init__.py` 文档
- v2 SSH 受限沙箱使用：`/Users/qianlan/Documents/CRM 读取能力.md`（运营私下分发，不要 commit）

---

**文档版本**：v1.0 / 2026-05-09
**最后实战验证**：5 月新版本激活 campaign（camp-d12ca96a7a58），66 人 batch dispatch 1 个 task 含 66 人成功
