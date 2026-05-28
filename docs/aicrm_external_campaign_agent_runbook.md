# AI-CRM 外部 Agent 定时 Campaign 调用手册

> 适用对象：Codex / OpenClaw / Claude Code / 自定义 Agent。<br>
> 当前状态：本文只记录当前代码已实现、可调用的接口能力。没有列在“已支持能力”里的场景，不要按旧文档猜接口调用。<br>
> 安全提醒：不要把真实 token 写进本文档、GitHub、前端代码、日志、飞书公开文档或审计备注。

---

## 1. 当前可用接口

当前接口分两类：

- 外部 Agent 创建/查询入口：给 Agent 使用，负责把明确的 `external_userid` 创建成可调度 Campaign。
- 后台 Campaign 管理入口：给运营后台、内部排障和受控运维使用，负责查看、审批、启动、暂停、编辑 step、查询成员和 run-due。

### 1.1 外部 Agent 创建/查询入口

| 能力 | 方法 | 路径 | 说明 |
|---|---:|---|---|
| 创建或预检外部 Campaign | POST | `/api/ai-assist/external/campaigns` | token 保护；支持单人、多人、每人定制话术、多天 step |
| 查询外部 Campaign 状态 | GET | `/api/ai-assist/external/campaigns/{campaign_code}` | token 保护；返回 campaign、steps、成员状态、排队 job 数 |

这两个接口挂在 `aicrm_next` FastAPI 应用下，响应里会带 `route_owner=ai_crm_next`。

### 1.2 后台 Campaign 管理入口

这些能力当前也必须保留。Next 生产架构下由 `aicrm_next.production_compat` 接管 `/api/admin/cloud-orchestrator/campaigns*`，再转发到现有 Campaign domain handler；响应头会带 `X-AICRM-Route-Owner: ai_crm_next`，并通过 compatibility facade 执行。

| 能力 | HTTP 方法 | 路径 | 当前用途 |
|---|---:|---|---|
| Campaign 列表 | GET | `/api/admin/cloud-orchestrator/campaigns` | 后台列表、按状态筛选 |
| Campaign 详情 | GET | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}` | 查看分层、steps、成员状态汇总 |
| 签发启动审批 token | POST | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}/approve` | 为人工启动签发一次性 token |
| 启动 Campaign | POST | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}/start` | 人工批准后启动 draft/paused Campaign |
| 批量启动同 group Campaign | POST | `/api/admin/cloud-orchestrator/campaigns/batch-start` | 按 `group_code` 批量审批并启动 |
| 暂停 Campaign | POST | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}/pause` | 暂停 active Campaign |
| 拒绝 Campaign | POST | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}/reject` | 拒绝并取消 Campaign |
| 删除 Campaign | DELETE | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}` | 删除非 active Campaign 及关联 steps/members/jobs |
| 扫描到期 Campaign 成员 | POST | `/api/admin/cloud-orchestrator/campaigns/run-due` | 内部定时器/受控运维扫描 due 成员 |
| 查询成员明细 | GET | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}/members` | 查看命中成员和发送状态 |
| 新增 step | POST | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}/steps` | 为可编辑 Campaign 追加 step |
| 更新 step | PATCH/POST | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}/steps/{step_index}` | 更新文案、时间、素材等 |
| 删除 step | DELETE | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}/steps/{step_index}` | 删除可编辑 Campaign 的 step |

外部 Agent 创建接口会自动完成创建、提交审阅、签发内部 approval token、启动、排 `broadcast_jobs`。上表这些后台接口仍然用于后台页面、人工运维和已有 Campaign 的生命周期管理，不应该删除。

---

## 2. 鉴权

服务端接受下面任一环境变量中的 token：

```bash
AICRM_EXTERNAL_CAMPAIGN_TOKEN
AUTOMATION_INTERNAL_API_TOKEN
```

Agent 调用时只通过环境变量注入，不要硬编码：

```bash
export AICRM_BASE_URL="https://www.youcangogogo.com"
export AICRM_AGENT_TOKEN="<configured-token>"
```

所有请求都带：

```bash
-H "Authorization: Bearer ${AICRM_AGENT_TOKEN}" \
-H "Content-Type: application/json"
```

也兼容 `X-Internal-Api-Token: ${AICRM_AGENT_TOKEN}`，但推荐 Bearer。

---

## 3. 已支持能力

当前接口支持：

- 输入 `external_userid` / `external_contact_id`
- 单人单步定时发送
- 单人多天持续跟进
- 多人统一话术
- 多人每人定制话术
- 多人每人多天定制话术
- `dry_run=true` 预检，不写 DB、不创建 campaign、不排 broadcast job
- 幂等创建：相同 `idempotency_key + group_code + owner_userid + external_userid + steps` 会生成稳定 `campaign_code`
- 默认校验联系人 owner：`contacts.owner_userid` 与请求 `owner_userid` 不一致时返回 409
- 自动创建一人 segment、一人 campaign、steps、campaign_member
- 自动提交审阅、签发内部 approval token、启动 campaign
- 自动通过现有 scheduler 生成未来 `broadcast_jobs`

当前接口不支持直接输入：

- 手机号
- 手机号前 3 后 4 mask
- segment_code
- previous_campaign_failed / previous_campaign_unreplied
- A/B test
- 每个用户多个 owner 自动择优

这些目标必须由 Agent 或上游系统先解析成明确的 `external_userid`，再调用本文接口。

---

## 4. 创建接口

```http
POST /api/ai-assist/external/campaigns
```

### 4.1 最小单人请求

```bash
curl -sS -X POST "${AICRM_BASE_URL}/api/ai-assist/external/campaigns" \
  -H "Authorization: Bearer ${AICRM_AGENT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "owner_userid": "HuangYouCan",
    "external_userid": "wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ",
    "scheduled_for": "2026-05-28 16:15",
    "timezone": "Asia/Shanghai",
    "message": "咱今天还报名吗？",
    "idempotency_key": "hyc_signup_wmbnxy_20260528_1615",
    "group_code": "hyc_signup_20260528",
    "group_label": "HuangYouCan 报名跟进 2026-05-28",
    "intent": "询问用户今天是否还报名"
  }'
```

说明：

- `scheduled_for` 支持 `YYYY-MM-DD HH:MM` 或 ISO datetime。
- 没有时区后缀时按 `timezone` 解释，默认 `Asia/Shanghai`。
- `message` 是单步话术；如果传 `steps`，以 `steps` 为准。
- `idempotency_key` 建议稳定传入；不要依赖 HTTP `Idempotency-Key` 头，当前实现使用 body 字段。

### 4.2 dry-run 预检

上线前或真实创建前，先加 `dry_run=true`：

```bash
curl -sS -X POST "${AICRM_BASE_URL}/api/ai-assist/external/campaigns" \
  -H "Authorization: Bearer ${AICRM_AGENT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "dry_run": true,
    "owner_userid": "HuangYouCan",
    "external_userid": "wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ",
    "scheduled_for": "2026-05-28 16:15",
    "timezone": "Asia/Shanghai",
    "message": "咱今天还报名吗？",
    "idempotency_key": "hyc_signup_wmbnxy_20260528_1615"
  }'
```

预期响应：

```json
{
  "ok": true,
  "dry_run": true,
  "side_effect_executed": false,
  "route_owner": "ai_crm_next",
  "recipient_count": 1,
  "campaigns": [
    {
      "campaign_code": "camp_ext_...",
      "external_userid": "wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ",
      "first_scheduled_for": "2026-05-28T16:15:00+08:00",
      "step_count": 1,
      "would_create": true
    }
  ]
}
```

### 4.3 多天 step

```json
{
  "owner_userid": "HuangYouCan",
  "external_userid": "wm_xxx",
  "timezone": "Asia/Shanghai",
  "group_code": "single_user_3day_followup",
  "group_label": "单人 3 天跟进",
  "intent": "连续 3 天跟进，回复后停止",
  "idempotency_key": "single_user_3day_followup_wm_xxx",
  "steps": [
    {
      "scheduled_for": "2026-05-28 10:30",
      "content_text": "第一条：我先把这件事跟你说清楚。",
      "stop_on_reply": true
    },
    {
      "day_offset": 1,
      "send_time": "10:30",
      "content_text": "第二条：昨天那条你可能还没来得及看。",
      "stop_on_reply": true
    },
    {
      "day_offset": 2,
      "send_time": "10:30",
      "content_text": "第三条：最后提醒一次，如果你需要我可以直接帮你开通。",
      "stop_on_reply": true
    }
  ]
}
```

第一步必须能推导出首发日期，可以用顶层 `scheduled_for`，也可以在第一条 step 写 `scheduled_for`。后续 step 可以用：

- `scheduled_for`
- 或 `day_offset + send_time`

`day_offset` 是相对第一步日期的天数。

### 4.4 多人统一话术

```json
{
  "owner_userid": "HuangYouCan",
  "external_userids": ["wm_001", "wm_002", "wm_003"],
  "scheduled_for": "2026-05-28 20:00",
  "timezone": "Asia/Shanghai",
  "message": "今晚有一场内部分享，我觉得你可以来听一下。",
  "group_code": "event_notice_20260528",
  "group_label": "今晚活动通知",
  "idempotency_key": "event_notice_20260528"
}
```

当前实现会为每个 `external_userid` 创建一个一人 campaign，并使用相同 `group_code` 聚合。这样可以支持每人不同话术，也便于单人失败隔离。

### 4.5 多人每人定制话术

```json
{
  "owner_userid": "HuangYouCan",
  "timezone": "Asia/Shanghai",
  "group_code": "v_invite_top20_whitelist_20260528",
  "group_label": "新版灰度邀请 Top20 2026-05-28",
  "intent": "新版灰度邀请，每人两条定制消息",
  "idempotency_key": "v_invite_top20_whitelist_20260528",
  "recipients": [
    {
      "external_userid": "wm_001",
      "display_name": "Susie",
      "steps": [
        {
          "scheduled_for": "2026-05-28 10:30",
          "content_text": "Susie，跟你说一件正经事——这次新版我觉得你很适合先试。",
          "stop_on_reply": true
        },
        {
          "day_offset": 1,
          "send_time": "10:30",
          "content_text": "Susie，跟进一下——如果这两天进来试用了，任何一个具体的小感受都对我们有用。",
          "stop_on_reply": true
        }
      ]
    },
    {
      "external_userid": "wm_002",
      "display_name": "Vicky",
      "steps": [
        {
          "scheduled_for": "2026-05-28 10:30",
          "content_text": "Vicky，这次新版我第一批想到你，主要是它跟你现在的业务节奏比较匹配。",
          "stop_on_reply": true
        },
        {
          "day_offset": 1,
          "send_time": "10:30",
          "content_text": "Vicky，昨天那条你可能没来得及看，我再补一句。",
          "stop_on_reply": true
        }
      ]
    }
  ]
}
```

---

## 5. 创建成功响应

```json
{
  "ok": true,
  "route_owner": "ai_crm_next",
  "source": "external_token_api",
  "group_code": "v_invite_top20_whitelist_20260528",
  "group_label": "新版灰度邀请 Top20 2026-05-28",
  "owner_userid": "HuangYouCan",
  "created_count": 2,
  "existing_count": 0,
  "campaigns": [
    {
      "campaign_code": "camp_ext_...",
      "campaign_id": 123,
      "external_userid": "wm_001",
      "segment_code": "seg_ext_...",
      "status": "created",
      "review_status": "approved",
      "run_status": "active",
      "anchor_date": "2026-05-28",
      "first_scheduled_for": "2026-05-28T10:30:00+08:00",
      "step_count": 2,
      "scheduled_jobs": 1
    }
  ]
}
```

注意：接口创建后会自动启动 campaign，并生成未来 `broadcast_jobs`。这不等于立即发送；真正发送由队列 worker 在 `scheduled_for` 到点后执行。

---

## 6. 查询状态

```bash
curl -sS -X GET "${AICRM_BASE_URL}/api/ai-assist/external/campaigns/${CAMPAIGN_CODE}" \
  -H "Authorization: Bearer ${AICRM_AGENT_TOKEN}"
```

响应结构：

```json
{
  "ok": true,
  "route_owner": "ai_crm_next",
  "campaign": {
    "campaign_code": "camp_ext_...",
    "review_status": "approved",
    "run_status": "active",
    "owner_userid": "HuangYouCan"
  },
  "segments": [],
  "member_status_counts": {
    "pending": 1
  },
  "total_members": 1,
  "scheduled_jobs": 1
}
```

---

## 7. 字段速查

### 7.1 顶层字段

| 字段 | 必填 | 说明 |
|---|---:|---|
| `owner_userid` / `sender` | 是 | 用哪个企微员工账号发送 |
| `external_userid` | 条件 | 单个目标用户；和 `external_contact_id` 等价 |
| `external_userids` | 条件 | 多个目标用户，统一话术 |
| `recipients` | 条件 | 多个目标用户，每人可定制话术 |
| `scheduled_for` | 条件 | 顶层首发时间；没有时第一条 step 必须提供 |
| `message` / `content_text` | 条件 | 单步统一话术；有 `steps` 时可省略 |
| `steps` | 否 | 多步统一话术 |
| `timezone` | 否 | 默认 `Asia/Shanghai` |
| `group_code` | 否 | 聚合标识；建议必传 |
| `group_label` | 否 | 人可读标题 |
| `intent` | 否 | 发送意图 |
| `idempotency_key` | 否 | 幂等键；建议必传 |
| `operator` | 否 | 默认 `external:{owner_userid}` |
| `dry_run` / `preview` | 否 | true 时只预检，不写 DB |
| `allow_owner_mismatch` | 否 | true 时允许联系人 owner 与请求 owner 不一致 |

至少需要 `external_userid`、`external_userids`、`recipients` 三者之一。

### 7.2 recipients 字段

| 字段 | 必填 | 说明 |
|---|---:|---|
| `external_userid` / `external_contact_id` | 是 | 明确的企微外部联系人 ID |
| `display_name` | 否 | 只用于展示命名 |
| `message` / `content_text` | 条件 | 该用户单步话术 |
| `steps` | 条件 | 该用户多步定制话术 |
| `campaign_code` | 否 | 指定 campaign_code；多人时会自动追加 hash 后缀 |

### 7.3 step 字段

| 字段 | 必填 | 说明 |
|---|---:|---|
| `scheduled_for` | 条件 | 该 step 的绝对发送时间 |
| `day_offset` | 条件 | 相对第一步日期的天数 |
| `send_time` | 条件 | `HH:MM` |
| `content_text` / `message` | 是 | 话术 |
| `stop_on_reply` | 否 | 默认 true |
| `content_payload` | 否 | 图片、小程序、附件等 payload |
| `skip_if_recently_touched_days` | 否 | 默认 0 |

---

## 8. 错误处理

| HTTP 状态 | error | 含义 |
|---:|---|---|
| 401 | `missing_internal_token` | 没带 token |
| 401 | `invalid_internal_token` | token 不匹配 |
| 503 | `external_campaign_token_not_configured` | 服务端没有配置 token |
| 400 | `scheduled_for is required` | 没有可推导的首发时间 |
| 400 | `message/content_text is required` | 没有话术 |
| 404 | `automation_member_not_found:{external_userid}` | 目标不在 `automation_member` |
| 409 | `owner_mismatch:...` | 联系人 owner 与请求 owner 不一致 |
| 409 | `target_headcount_invalid:...` | 单人 segment 没有精确命中 1 人 |

Agent 规则：

- 401/503：停止，要求配置 token。
- 404：停止，要求用户提供可触达的 `external_userid`。
- 409 owner mismatch：默认停止；除非用户明确允许改用该 owner 或设置 `allow_owner_mismatch=true`。
- 任何 500：不要重试大量请求；先反馈错误并查服务日志。

---

## 9. Agent 标准流程

```text
1. 把用户输入解析成 external_userid 列表。
2. 确定 owner_userid。
3. 确定首发时间，必须是未来时间。
4. 生成稳定 idempotency_key 和 group_code。
5. 先 dry_run=true 调预检。
6. dry_run 通过后，移除 dry_run 再真实创建。
7. 返回 group_code、campaign_code、scheduled_jobs、状态查询命令。
8. 不要手动调用 run-due 或直接写 DB。
```

Agent 给用户的成功回复模板：

```text
已创建定时 Campaign。

- group_code: xxx
- owner_userid: HuangYouCan
- campaign_code: camp_ext_xxx
- 首发时间: 2026-05-28 16:15 Asia/Shanghai
- step_count: 1
- scheduled_jobs: 1
- review_status: approved
- run_status: active

当前还不是“已发送”，会在 scheduled_for 到点后由 broadcast queue worker 执行。
```

---

## 10. 截图场景的当前标准做法

截图里的“Top20 每人两条定制消息”当前按下面方式实现：

```text
1 个 group_code
N 个一人 campaign
每个 campaign 1 个 campaign_member
每个 campaign 内 N 条 campaign_steps
每个 campaign 启动后生成未来 broadcast_jobs
```

这和旧设想的 `campaign_member_steps` 不同。当前代码没有 `campaign_member_steps` 表；不要在文档或 Agent 行为里假设它存在。

如果上游只有手机号、phone mask 或白名单名称，必须先通过别的可用数据能力解析成：

```json
[
  {
    "external_userid": "wm_xxx",
    "owner_userid": "HuangYouCan",
    "steps": []
  }
]
```

再调用本文接口。

---

## 11. 最小验收

### 11.1 本地测试

```bash
.venv/bin/python -m pytest -q tests/test_ai_assist_external_campaigns.py
.venv/bin/python -m py_compile aicrm_next/ai_assist/external_campaigns.py aicrm_next/ai_assist/api.py
```

### 11.2 生产 dry-run

```bash
curl -sS -X POST "${AICRM_BASE_URL}/api/ai-assist/external/campaigns" \
  -H "Authorization: Bearer ${AICRM_AGENT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "dry_run": true,
    "owner_userid": "HuangYouCan",
    "external_userid": "wm_xxx",
    "scheduled_for": "2026-05-28 16:15",
    "message": "smoke test",
    "idempotency_key": "smoke_external_campaign"
  }'
```

要求：

```text
ok=true
dry_run=true
side_effect_executed=false
route_owner=ai_crm_next
campaigns[0].would_create 明确
```

### 11.3 生产真实创建

只在 dry-run 通过、用户确认后执行真实创建。创建后马上 GET 状态接口确认：

```bash
curl -sS -X GET "${AICRM_BASE_URL}/api/ai-assist/external/campaigns/${CAMPAIGN_CODE}" \
  -H "Authorization: Bearer ${AICRM_AGENT_TOKEN}"
```

要求：

```text
ok=true
run_status=active
scheduled_jobs >= 1
```

---

## 12. 不要再使用的旧路径

旧文档里的这些路径当前不是本文能力的一部分，不要让 Agent 调用：

```text
POST /api/external/ai-campaigns/resolve-targets
POST /api/external/ai-campaigns
POST /api/external/ai-campaigns/{campaign_code}/submit-review
GET  /api/external/ai-campaigns/{campaign_code}
```

当前有效路径是：

```text
POST /api/ai-assist/external/campaigns
GET  /api/ai-assist/external/campaigns/{campaign_code}
```
