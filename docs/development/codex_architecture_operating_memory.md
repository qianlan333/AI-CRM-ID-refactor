# AI-CRM Codex 强制架构同步与开发执行规范

> 建议保存路径：`docs/development/codex_architecture_operating_memory.md`  
> 建议用途：作为 Codex / AI 开发代理的强制长期记忆与每次任务启动前的同步规范。  
> 本文档不授权生产切换、不授权真实外呼、不授权删除 legacy fallback、不授权修改 nginx/systemd/deploy 生产配置。

---

## 0. 本文档的定位

本文档是 AI-CRM 后续开发的“强制操作记忆”。

Codex 或任何 AI 开发代理在处理 AI-CRM 仓库任务时，必须把本文档作为优先级高于普通任务描述的开发约束。

如果用户的任务描述与本文档冲突，默认以本文档为准，除非用户在当前任务中明确写出：

- 本次允许触碰生产数据；
- 本次允许切换 production route owner；
- 本次允许删除 legacy fallback；
- 本次允许启用真实 WeCom / Payment / OAuth / OpenClaw / MCP / timer / outbound send；
- 本次允许修改 nginx / systemd / deploy 生产配置；
- 本次已有 owner approval、rollback plan、checker 和 smoke evidence。

没有这些明确授权时，Codex 必须按安全路径开发。

---

## 1. 每次开发前必须先同步的文件

每次开始 AI-CRM 任务前，Codex 必须先读取并遵循以下文件：

```text
README.md
docs/llm_handoff.md
docs/project_map.md
docs/development/ai_crm_next_architecture_skill.md
skills/ai-crm-next-architecture/SKILL.md
docs/route_ownership/production_route_ownership_manifest.yaml
docs/development/legacy_replacement_backlog.yaml
```

如果任务涉及自动化转化，还必须读取：

```text
docs/automation_conversion_acceptance_support_package.md
docs/automation_conversion_business_acceptance.md
docs/automation_conversion_local_runbook.md
```

如果任务涉及 MCP / OpenClaw，还必须读取：

```text
docs/mcp_usage.md
docs/openclaw_crm_read_contract.md
```

如果任务涉及部署或生产环境，还必须读取：

```text
docs/deploy_runbook.md
```

---

## 2. 当前架构事实：不能重新解释，也不能绕过

AI-CRM 当前架构事实如下：

1. GitHub `main` 是唯一源码主线。
2. 默认 runtime 是 AI-CRM Next FastAPI modular monolith。
3. `python3 app.py run` 默认启动 `aicrm_next.main:app`。
4. legacy Flask 只作为显式 fallback 和 production compatibility facade。
5. `wecom_ability_service/` 保留为 legacy fallback，不是新功能默认开发入口。
6. `openclaw_service/` 和 `legacy_flask/openclaw_legacy/` 已物理删除，不得重新引入。
7. MCP / OpenClaw 后续只允许通过 `aicrm_next.integration_gateway` adapter boundary 承接。
8. 真实 WeCom / Payment / OAuth / OpenClaw / MCP / timer / outbound send 默认 blocked / fake / staging-disabled。
9. fixture / local_contract / demo 数据不得伪装成 production success。
10. production owner 切换、fallback 删除、生产写入、生产外呼都必须另行审批。

---

## 3. AI-CRM Next 的业务分区

后续开发必须先判断任务属于哪个 capability owner。

| Capability owner | 业务含义 | 典型范围 |
|---|---|---|
| `aicrm_next.platform_foundation` | 系统基础能力 | health、runtime、timer safe-mode、系统状态 |
| `aicrm_next.frontend_compat` | 后台页面兼容层 | admin shell、旧页面兼容、只渲染页面 |
| `aicrm_next.customer_read_model` | 客户只读模型 | 客户列表、详情、时间线、最近消息、客户画像只读 |
| `aicrm_next.identity_contact` | 身份识别与绑定 | sidebar 绑定状态、openid/unionid/external_userid 映射 |
| `aicrm_next.questionnaire` | 问卷能力 | 问卷后台、H5 问卷、提交、OAuth、标签写回相关边界 |
| `aicrm_next.automation_engine` | 自动化转化 | program、pool、workflow、task、action-template、profile-segment-template、execution |
| `aicrm_next.commerce` | 商品与支付 | 商品、订单、交易、微信支付、支付宝 |
| `aicrm_next.media_library` | 素材库 | 图片、附件、小程序素材 |
| `aicrm_next.ai_assist` | AI 辅助能力 | campaign、agent、AI 生成、辅助分析 |
| `aicrm_next.integration_gateway` | 外部系统与旧系统边界 | WeCom、MCP、OpenClaw、OAuth、Payment、legacy facade、adapter contract |
| `aicrm_next.shared` / infrastructure | 通用基础能力 | DB provider、runtime config、audit、idempotency、errors、repository provider |

---

## 4. 开发分层：每层只能做自己的事

Codex 必须按以下分层开发，不得为了省事跨层乱调。

| 层 | 可以做什么 | 不可以做什么 |
|---|---|---|
| API / HTTP / `frontend_compat` | 解析请求、调用 application query/command、返回响应、渲染页面 | 不直接写 SQL；不直接 import 其他 context 的 repo/service；不塞复杂业务规则 |
| application | 编排业务用例、组合 domain/repository/gateway | 不直接处理外部协议细节；不绕过领域校验 |
| domain | 本业务上下文的规则、状态、校验、投影 | 不访问数据库；不调用外部系统 |
| read model | 只读投影、只读查询组合 | 不承接写逻辑 |
| repository | 数据读取/写入适配 | 不做跨 context 业务编排 |
| integration_gateway | 外部协议、legacy facade、MCP、OpenClaw、WeCom、Payment、OAuth | 不默认打开真实外呼；不绕过 approval |
| shared / infrastructure | runtime、配置、DB provider、审计、幂等、通用错误 | 不承接具体业务需求 |

---

## 5. 每次任务开始前，Codex 必须先输出“任务边界确认”

在写代码前，Codex 必须先在任务回复或 PR 描述里回答以下问题：

```text
1. 本任务的业务目标是什么？
2. 本任务对业务有什么帮助？
3. 本任务属于哪个 capability owner？
4. 涉及哪些 route family？
5. 这些 route 当前 owner 是什么？
   - next
   - frontend_compat
   - production_compat
   - legacy_forward
   - fake_adapter
   - guarded_preview
   - scheduled_safe_mode
   - real_blocked
6. 本任务是否涉及生产数据？
7. 本任务是否涉及真实外部调用？
8. 本任务是否有 fixture/local_contract/demo 数据风险？
9. 本任务是否需要更新 route ownership manifest？
10. 本任务是否需要新增或更新 checker？
11. 本任务的 rollback 是什么？
12. 本任务明确不做什么？
```

如果不能回答这些问题，不能开始开发。

---

## 6. 业务价值必须写清楚

每个任务、每个 PR 都必须单独写 “Business value / 业务帮助”。

业务帮助必须用非编程语言说明，例如：

```text
本 PR 对业务的帮助：
- 保持现有后台自动化转化页面可用，不中断当前运营配置。
- 为 action-template 未来从旧系统迁移到 Next 做安全准备。
- 通过幂等和 audit 设计，降低重复提交、误操作、无法回滚的风险。
- 本阶段不碰生产写入，所以不会影响当前客户运营流程。
```

禁止只写：

```text
- Added repository adapter
- Added tests
- Refactored API
```

开发不是为了“改代码”，而是为了让业务能力更稳定地迁移、恢复、扩展。

---

## 7. route ownership 是最高优先级约束之一

任何涉及页面或接口的任务，必须先查：

```text
docs/route_ownership/production_route_ownership_manifest.yaml
```

必须确认：

```text
route_pattern
methods
capability_owner
current_runtime_owner
production_behavior
legacy_fallback_allowed
fixture_allowed_in_production
external_side_effect_risk
delete_ready
checker
notes
```

### 7.1 如果 route 当前是 `next`

可以在 Next 内部增强，但仍要保持 checker、测试、fallback 规则和生产数据安全。

### 7.2 如果 route 当前是 `frontend_compat`

只能做页面 shell / 兼容渲染 / 只读展示层增强。

禁止在 `frontend_compat` 里新增直接 SQL、复杂业务规则、外部调用。

### 7.3 如果 route 当前是 `production_compat` / `legacy_forward`

默认说明生产路径仍由旧系统兜底。

此时允许做：

- Next native contract planning；
- fixture/local contract；
- local parity harness；
- test DB parity；
- staging smoke package；
- staging evidence gate；
- production dry-run planning。

默认不允许做：

- 切 production owner；
- 删除 legacy fallback；
- 修改 production_compat catch-all；
- 写生产；
- 执行真实外部调用。

### 7.4 如果 route 是 `fake_adapter` / `real_blocked`

默认不能打开真实外部调用。

必须先补：

- adapter contract；
- fake/staging-disabled evidence；
- approval checklist；
- audit；
- idempotency；
- rollback；
- external side-effect safety checker。

---

## 8. Legacy Growth Freeze

后续新功能默认走 AI-CRM Next native implementation。

legacy 只能作为：

1. production compatibility；
2. rollback；
3. hotfix；
4. 对照参考；
5. 旧生产路径未迁移完成前的兜底。

禁止事项：

- 禁止新增 legacy 作为新功能主入口；
- 禁止绕过 import guard 动态 import legacy；
- 禁止重新引入 `openclaw_service/`；
- 禁止重新引入 `legacy_flask/openclaw_legacy/`；
- 禁止扩大 `production_compat` catch-all 而不更新 manifest 和 checker；
- 禁止在 PR 中把 legacy fallback 描述成新的目标架构。

---

## 9. fixture/local_contract/demo 数据安全

fixture/local_contract/demo 只允许用于：

- 本地开发；
- contract shape 验证；
- local parity；
- checker；
- 单元测试；
- staging 前的结构确认。

禁止用于：

- production success；
- production approval；
- production canary；
- route-switch readiness；
- “已经上线成功”的证据；
- 真实业务验收。

如果 production data unavailable，应该返回 degraded / blocked / error，而不是返回 fixture 假成功。

---

## 10. 外部调用默认禁止

以下能力默认禁止真实调用，除非任务明确批准并附带审批、审计、幂等、回滚和 checker：

```text
WeCom
Payment
OAuth
OpenClaw
MCP
timer
automation execution
outbound send
media upload
customer pool state change
agent runtime execution
workflow runtime execution
external webhook dispatch
```

如果任务只是开发 contract / adapter / fake / staging-disabled，不得偷偷打开真实外呼。

所有外部系统相关工作都必须经过：

```text
aicrm_next.integration_gateway
```

---

## 11. Phase 节奏

后续开发按阶段推进，不得跳级。

| Phase | 类型 | 目标 | 默认限制 |
|---|---|---|---|
| Phase 3 | readonly | 只读能力迁移与生产只读 facade | 不写生产，不删 fallback |
| Phase 4 | internal_write | 内部配置写能力，例如模板、任务、工作流 | 必须有幂等、audit、rollback、checker；默认不切生产 owner |
| Phase 5 | external_adapter | WeCom / Payment / OAuth / OpenClaw / MCP 等外部适配 | 默认 fake/staging-disabled，真实外呼需审批 |
| Phase 6 | timer / automation execution | 定时任务、自动执行、自动发送 | 默认 scheduled_safe_mode，真实执行需强审批 |

当前自动化转化相关任务通常属于 Phase 4 internal_write。

---

## 12. Phase 4 internal_write 的标准推进阶梯

对于 action-templates、profile-segment-templates、task-groups、tasks、workflows、workflow-nodes、agents、executions 等内部写能力，建议按以下顺序推进：

```text
1. legacy discovery / native contract planning
2. schema / route / service behavior confirmation
3. companion idempotency / audit schema planning
4. additive migration artifact
5. fixture/local native contract
6. local parity harness
7. repository adapter planning
8. repository adapter behind explicit flag
9. local/test DB parity
10. staging smoke package
11. staging smoke evidence gate
12. production dry-run planning
13. production read-only dry-run / guarded write dry-run
14. owner approval closure
15. production route owner switch
16. fallback narrowing
17. fallback deletion is forbidden unless delete_ready=true
```

不能跳过中间证据直接切生产。

---

## 13. PR 必须包含的结构

每个 PR 描述必须包含：

```text
## Summary

## Architecture boundary

## Business continuity

## Business value

## Safety / non-goals

## Verification

## Risk / rollback

## Phase decision

## Next action

## PR lifecycle
```

### 13.1 Summary

说明本 PR 做了什么。

### 13.2 Architecture boundary

必须说明：

```text
- Capability owner:
- Route family:
- Current runtime owner:
- Production behavior:
- 是否改变 production owner:
- 是否连接生产数据:
- 是否启用真实外呼:
- 是否修改 production_compat:
- 是否删除 fallback:
```

### 13.3 Business continuity

必须说明本 PR 如何保证现有业务不断。

必须明确：

```text
不影响当前线上日常使用。
不删除 legacy fallback。
不切 production route owner。
不把 fixture/local_contract 当 production success。
如果生产数据不可用，返回 degraded/blocked/error，而不是假成功。
```

### 13.4 Business value

必须用业务语言说明这次的价值。

### 13.5 Safety / non-goals

必须明确本 PR 不做什么。

常见 non-goals：

```text
- 不连接 production DB
- 不写 production
- 不启用真实 WeCom / Payment / OAuth / OpenClaw / MCP / timer / outbound send
- 不修改 nginx/systemd/deploy production 配置
- 不删除 legacy fallback
- 不切 production owner
- 不实现 out-of-scope route
```

### 13.6 Verification

必须列出实际运行的 checker/test 命令。

至少包括：

```text
python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json
python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json
git diff --check
```

并添加任务专属 checker/test。

如任务涉及 architecture skill，建议加：

```text
.venv/bin/python tools/check_architecture_skill_compliance.py --output-md /tmp/architecture_skill_compliance.md --output-json /tmp/architecture_skill_compliance.json
```

### 13.7 Risk / rollback

必须说明：

```text
- 风险范围
- 如何回滚
- 回滚是否影响生产数据
- 如果有 staging write，cleanup 限定在哪个 safe namespace
```

### 13.8 Phase decision

必须明确：

```text
本阶段只完成什么。
哪些事情未授权。
下一阶段是否需要 owner 显式确认。
```

### 13.9 Next action

必须给出下一步，但不能越权。

例如：

```text
如果 staging evidence blocked，下一阶段继续补 staging approval/config。
如果 staging evidence passed，下一阶段可以做 production dry-run planning。
仍不得切 production owner，不得写 production，不得删除 fallback。
```

---

## 14. Codex 开发前固定提示词

后续用户可以直接把下面这段发给 Codex：

```text
请先读取并严格遵循：

- docs/development/codex_architecture_operating_memory.md
- docs/development/ai_crm_next_architecture_skill.md
- skills/ai-crm-next-architecture/SKILL.md
- docs/route_ownership/production_route_ownership_manifest.yaml
- docs/development/legacy_replacement_backlog.yaml

本次任务开始前，必须先输出“任务边界确认”，回答：

1. 本任务的业务目标是什么？
2. 本任务对业务有什么帮助？
3. capability owner 是谁？
4. 涉及哪些 route family？
5. 当前 route owner / production behavior 是什么？
6. 是否涉及生产数据？
7. 是否涉及真实外部调用？
8. 是否存在 fixture/local_contract/demo 数据风险？
9. 是否需要更新 route ownership manifest？
10. 是否需要新增或更新 checker？
11. rollback 是什么？
12. 本次明确不做什么？

在我没有明确授权前，禁止：
- 切 production owner
- 删除 legacy fallback
- 修改 production_compat catch-all
- 写 production
- 启用真实 WeCom / Payment / OAuth / OpenClaw / MCP / timer / outbound send
- 修改 nginx/systemd/deploy 生产配置
- 把 fixture/local_contract/demo 当成 production success
- 把 checker 本地结果写成 production canary evidence

PR 必须包含：
Summary / Architecture boundary / Business continuity / Business value / Safety / non-goals / Verification / Risk / rollback / Phase decision / Next action / PR lifecycle。

每个 PR 都必须单独写清楚“这次对业务有什么帮助”。
```

---

## 15. 用户给 Codex 的任务描述模板

```text
任务名称：
[填写任务名称]

业务目标：
[用非技术语言说明要恢复、增强或迁移什么能力]

涉及范围：
[填写 route family，例如 /api/admin/automation-conversion/action-templates*]

预期业务帮助：
- [帮助 1]
- [帮助 2]
- [帮助 3]

当前限制：
- 不切 production owner
- 不删除 legacy fallback
- 不修改 production_compat catch-all
- 不连接 production DB
- 不写 production
- 不启用真实外部调用
- 不修改 nginx/systemd/deploy 生产配置
- 不把 fixture/local_contract/demo 当 production success

开发要求：
1. 先读 docs/development/codex_architecture_operating_memory.md。
2. 先输出任务边界确认。
3. 根据 route ownership manifest 判断当前 owner。
4. 按当前 phase 只做本阶段允许的事情。
5. 补齐任务专属 checker/test。
6. PR 必须写清 Business continuity 和 Business value。
7. 给出 rollback。
8. 给出 Next action，但不得越权。
```

---

## 16. 用户验收 PR 时的检查清单

用户不需要懂代码，只要检查 PR 说明是否包含以下内容。

```text
[ ] 是否写了 capability owner？
[ ] 是否写了 route family？
[ ] 是否写了 current runtime owner / production behavior？
[ ] 是否明确不切 production owner？
[ ] 是否明确不删除 legacy fallback？
[ ] 是否明确不启用真实外部调用？
[ ] 是否明确不写 production？
[ ] 是否说明 fixture/local_contract/demo 不能当 production success？
[ ] 是否写了 Business continuity？
[ ] 是否写了 Business value？
[ ] 是否列出 checker/test 命令？
[ ] 是否写了 rollback？
[ ] 是否写了 Phase decision？
[ ] 是否写了 Next action？
```

如果缺少任何一项，用户可以要求 Codex 先补 PR 描述或补 checker，不要急着合并。

---

## 17. 常见越界信号

看到以下表述时，需要暂停开发或要求 Codex 重做边界确认。

### 17.1 危险表述

以下是未经授权禁止使用的状态词和表述：

```text
production_ready
production_approved
delete_ready
canary passed
real external call enabled
fallback removed
route owner switched
直接复用 legacy service
直接在 frontend_compat 查询数据库
临时打开真实企微调用
临时用 DATABASE_URL
fixture 数据可用于生产验证
```

### 17.2 正确表述

以下是授权前允许使用的安全表述：

```text
planning only
fixture/local contract only
staging evidence only
production dry-run planning only
blocked evidence
degraded production unavailable
legacy fallback remains
production owner unchanged
real external calls remain blocked
delete_ready is explicitly forbidden and remains false
```

---

## 18. 自动化转化后续开发的默认策略

自动化转化是当前最复杂也最容易乱的区域。

默认按 route family 拆，不要一次性大改。

优先顺序建议：

```text
1. profile-segment-templates
2. action-templates
3. task-groups
4. tasks
5. workflows
6. workflow-nodes
7. agents
8. agent-outputs
9. agent-runs
10. executions
11. run-due / timer / outbound send 最后做
```

每组都要单独完成：

```text
planning
contract
schema/audit/idempotency
fixture/local
test DB
staging
production dry-run
approval
owner switch
fallback narrowing
```

---

## 19. 对 Codex 的最终硬性要求

Codex 在 AI-CRM 仓库中执行任何开发任务时，必须遵守：

1. 先同步架构记忆，再开发。
2. 先确认 route owner，再改代码。
3. 先说明业务价值，再写技术实现。
4. 先保护现有业务，再迁移新架构。
5. 先 fixture/local，再 test DB，再 staging，再 production dry-run。
6. 没有 approval，不切 production owner。
7. 没有 checker，不合并。
8. 没有 rollback，不合并。
9. 没有 Business continuity，不合并。
10. 没有 Business value，不合并。
11. 不把本地成功说成生产成功。
12. 不把 staging evidence 说成 production approval。
13. 禁止把 legacy fallback 删除当作重构成果，除非 `delete_ready=true` 且有审批。
14. 不为了完成任务绕过 architecture skill。
15. 不为了省事把复杂逻辑塞进 API / frontend_compat。

---

## 20. 本文档的维护方式

当 AI-CRM 架构发生变化时，必须同步更新：

```text
docs/development/codex_architecture_operating_memory.md
docs/development/ai_crm_next_architecture_skill.md
skills/ai-crm-next-architecture/SKILL.md
docs/route_ownership/production_route_ownership_manifest.yaml
docs/development/legacy_replacement_backlog.yaml
```

任何修改本文档的 PR 也必须通过：

```text
tools/check_architecture_skill_compliance.py
tools/check_legacy_facade_growth_freeze.py
tools/generate_legacy_replacement_backlog.py --check
```

---

## 21. 一句话总规则

> AI-CRM 后续开发不是“让 Codex 快速改完功能”，而是“让 Codex 在不破坏现有业务的前提下，按 route ownership 和 phase evidence 一块一块把能力迁到 AI-CRM Next”。
