# 自动化转化线上总验收 Checklist

## 配置检查

- [ ] `AUTOMATION_INTERNAL_API_TOKEN` 已配置
- [ ] `MCP_BEARER_TOKEN` 如仍保留 legacy 兼容，已确认与统一 token 不冲突
- [ ] `OPENCLAW_WEBHOOK_URL` 已配置
- [ ] `AUTOMATION_ACTIVATION_WEBHOOK_TOKEN` 如仍保留 legacy 兼容，已确认与统一 token 不冲突
- [ ] `QUESTIONNAIRE_SUBMIT_WEBHOOK_URL` 已配置
- [ ] `QUESTIONNAIRE_SUBMIT_WEBHOOK_TOKEN` 已配置
- [ ] `MESSAGE_ACTIVITY_DB_HOST/PORT/NAME/USER/PASS` 已配置
- [ ] 企微相关配置已配置
- [ ] 错误内部 token 调动作型接口会返回 401

## 问卷检查

- [ ] 自动化转化问卷已配置
- [ ] 问卷包含必填手机号题
- [ ] 关键题配置正常
- [ ] 提交成功后手机号正常保存

## 池子检查

- [ ] 新用户池可进入
- [ ] 未激活普通池可进入
- [ ] 未激活重点跟进池可进入
- [ ] 激活普通池可进入
- [ ] 激活重点跟进池可进入
- [ ] 沉默池可进入

## 侧边栏检查

- [ ] 当前池子展示正确
- [ ] 当前是否激活展示正确
- [ ] 当前跟进类型展示正确
- [ ] 普通/重点人工改判可用
- [ ] 人工确认成交可用

## 自动化转化群发检查

- [ ] 首页每个阶段都能点击 `创建群发`
- [ ] `new-user / inactive-normal / active-normal / silent / won` 可走官方群发
- [ ] 官方群发当前只支持 `文本 + 附件(file media_id)`
- [ ] 当前按单发送人模型执行，不做 owner filter / owner 分桶
- [ ] `inactive-focus / active-focus` 可创建 OpenClaw AI 批任务
- [ ] AI 批任务通过后台 runner 推进，不在请求里 sleep
- [ ] 发送记录可查

## 焦点消息 webhook 检查

- [ ] 重点跟进池客户来消息会推送 webhook
- [ ] 普通池客户来消息不会推送
- [ ] payload 关键字段完整
- [ ] 失败日志可查

## 激活回写检查

- [ ] 按手机号回写成功
- [ ] 未激活普通 -> 激活普通
- [ ] 未激活重点 -> 激活重点
- [ ] 已激活重复回写只刷新时间

## 问卷提交 webhook 检查

- [ ] 提交成功后会外发 webhook
- [ ] 字段为 mobile / userid / unionid
- [ ] webhook 异常不影响问卷主提交流程

## 成交退出营销检查

- [ ] 人工确认成交后状态变成 `converted/enrolled`
- [ ] 成交后不再 eligible for conversion

## 日志 / 发送记录检查

- [ ] service 日志能看到关键动作
- [ ] 发送记录能查到官方群发记录
- [ ] focus batch 和 item 状态可查
- [ ] webhook 失败有日志痕迹

## 异常处理与回退检查

- [ ] OpenClaw webhook 可单独停用
- [ ] 问卷 webhook 可单独停用
- [ ] 激活回写入口可单独停用
- [ ] 池子群发可单独停用
- [ ] 自动化转化问卷初判可整体停用
