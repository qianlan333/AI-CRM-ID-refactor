# 自动化转化线上总验收 Runbook

## 1. 目标

把自动化转化 1-7 能力整理成一套可执行的线上总验收顺序，确保：

- 配置齐全
- 主链路可跑
- 关键日志可查
- 风险可控
- 出问题时可快速降级

## 2. 线上部署前前置条件

上线前必须先确认：

1. 代码目录已经同步到生产目录
2. Python 依赖已经安装完成
3. `python app.py init-db` 已执行完成
4. `openclaw-wecom-postgres.service` 已重启成功
5. `/health` 返回正常
6. 后台能正常打开：
   - `/admin`
   - `/admin/questionnaires`
   - `/admin/automation-conversion`
7. 自动化转化问卷已经配置完成
8. 至少准备好 2 个线上验收客户：
   - 普通路径客户
   - 重点跟进路径客户

## 3. 线上必须确认的配置项

必须在线上可用：

- `AUTOMATION_INTERNAL_API_TOKEN`
- `MCP_BEARER_TOKEN`（仅 legacy 兼容需要时保留）
- `OPENCLAW_FOCUS_MESSAGE_WEBHOOK_URL`
- `OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TOKEN`
- `OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TIMEOUT_SECONDS`
- `AUTOMATION_ACTIVATION_WEBHOOK_TOKEN`（仅 legacy 兼容需要时保留）
- `QUESTIONNAIRE_SUBMIT_WEBHOOK_URL`
- `QUESTIONNAIRE_SUBMIT_WEBHOOK_TOKEN`
- `QUESTIONNAIRE_SUBMIT_WEBHOOK_TIMEOUT_SECONDS`
- `WECOM_CORP_ID`
- `WECOM_SECRET`
- `WECOM_CONTACT_SECRET`
- `WECOM_AGENT_ID`
- `WECOM_API_BASE`

当前第 4 块和第 5 块按真实 `owner_userid` 生效，线上总验收至少准备两个不同负责人的样本客户更稳妥。

## 4. 线上哪些 webhook 地址必须可用

至少要确认以下地址在线：

1. `OPENCLAW_FOCUS_MESSAGE_WEBHOOK_URL`
   - 重点跟进池客户来消息时使用
2. `QUESTIONNAIRE_SUBMIT_WEBHOOK_URL`
   - 问卷提交成功后外发
3. `POST /api/customers/automation/activation-webhook`
   - 外部系统激活回写入口

## 5. 线上总验收执行顺序

建议顺序：

1. 健康检查
2. 配置检查
3. 问卷检查
4. 普通路径 smoke
5. 重点跟进路径 smoke
6. 异常路径 smoke
7. 日志和发送记录检查
8. 降级/止损动作确认

## 6. 线上 smoke 检查顺序

### 普通路径 smoke

1. 提交问卷
2. 确认手机号正常保存
3. 写入 trial_opened 事实
4. 确认进入未激活普通池
5. 激活回写
6. 确认进入激活普通池
7. 验证可继续标准跟进
8. 人工确认成交
9. 确认退出营销

### 重点跟进路径 smoke

1. 提交问卷
2. 命中重点跟进
3. 写入 trial_opened 事实
4. 确认进入未激活重点跟进池
5. 客户来消息
6. 确认触发 OpenClaw webhook
7. 激活回写
8. 确认进入激活重点跟进池
9. 触发池子群发
10. 人工确认成交
11. 确认退出营销

### 异常路径 smoke

推荐优先验证：

- 沉默池不可群发

也可以补充验证：

- 问卷提交 webhook 失败但主流程不失败

## 7. 线上只读 smoke 顺序

先做只读检查，再做写操作：

```bash
curl -sS http://127.0.0.1:5001/health
sudo systemctl status openclaw-wecom-postgres.service --no-pager
sudo journalctl -u openclaw-wecom-postgres.service -n 100 --no-pager
```

后台只读确认：

- `/admin/automation-conversion`
- `/admin/questionnaires`
- `/admin/customers`

## 8. 如果发现问题，怎么快速回退到“只读/停用”状态

### 8.1 OpenClaw webhook 异常

止损动作：

- 把 `OPENCLAW_FOCUS_MESSAGE_WEBHOOK_URL` 清空

影响：

- 重点跟进池来消息不再推送 OpenClaw
- CRM 主链路、问卷、切池、侧边栏、激活回写不受影响

### 8.2 问卷提交外发 webhook 异常

止损动作：

- 把 `QUESTIONNAIRE_SUBMIT_WEBHOOK_URL` 清空

影响：

- 问卷仍可正常提交
- 只是不再外发 mobile / userid / unionid webhook

### 8.3 激活回写 webhook 异常

止损动作：

- 临时下掉外部调用方
- 或把 `AUTOMATION_INTERNAL_API_TOKEN` 换成新值，拒绝旧流量
- 如果仍保留 legacy 兼容，再同步轮换 `AUTOMATION_ACTIVATION_WEBHOOK_TOKEN`

影响：

- 激活回写入口暂停
- 其它主链路不受影响

### 8.4 池子群发异常

止损动作：

- 暂停使用 MCP 工具 `send_pool_private_message`
- 或临时替换 `AUTOMATION_INTERNAL_API_TOKEN`
- 如果仍保留 legacy 兼容，再同步替换 `MCP_BEARER_TOKEN`

影响：

- OpenClaw 无法再直接发起池子群发
- CRM 其它链路不受影响

### 8.5 需要临时停自动化转化

止损动作：

- 进入 `/admin/automation-conversion`
- 关闭“开启自动化转化问卷初判”

影响：

- 自动化转化问卷初判和后续路由停止继续推进
- 已有历史记录仍保留
- 手工侧边栏查看和人工动作仍可继续

## 9. 如果发现 webhook 异常怎么降级

推荐降级顺序：

1. 先只停出问题的 webhook
2. 保留 CRM 主流程
3. 继续做只读验收和人工验收
4. 如果问题扩散到核心切池或提交链路，再考虑关闭自动化转化开关

## 10. 线上日志检查建议

优先查：

```bash
sudo journalctl -u openclaw-wecom-postgres.service -f
```

关注关键词：

- `questionnaire submit webhook`
- `openclaw focus message webhook`
- `activation_webhook`
- `send_pool_private_message`
- `invalid internal token`
- `missing internal token`

## 11. 统一鉴权核对建议

线上至少验证以下动作型接口都被统一 Bearer Token 保护：

1. `/mcp`
2. `/api/customers/automation/activation-webhook`
3. `/api/customers/automation/webhook-deliveries/retry-due`
4. `/api/admin/jobs/webhook-deliveries/run`

最小核对方法：

- 正确 token 调用返回成功
- 错 token 调用统一返回 `401`
- 公开问卷提交接口 `/api/h5/questionnaires/<slug>/submit` 仍保持可用

同时检查：

- 后台发送记录
- 客户当前池子
- 侧边栏状态
