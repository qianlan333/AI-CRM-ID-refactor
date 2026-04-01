# 05 Tool Catalog

## 工具总表

### `resolve_customer`

用途：

- 通过手机号或 `external_userid` 解析客户

典型场景：

- OpenClaw 拿到手机号，先把它转成 CRM 可识别的客户身份

### `get_customer_context`

用途：

- 获取客户上下文

典型场景：

- 查看客户基础信息、最近消息、最近时间线

### `list_questionnaires`

用途：

- 列出用户运营看板 v2 可读的表单/问卷

典型场景：

- OpenClaw 先拿到当前有哪些表单，再决定读取哪一份

### `get_questionnaire`

用途：

- 查看单个表单/问卷的结构

典型场景：

- 读取题目、选项、分数规则，理解这个表单采集什么信息

### `get_questionnaire_submissions`

用途：

- 查看单个表单/问卷的提交结果预览

典型场景：

- OpenClaw 读取最近提交数据、理解表单回答情况，不直接做写入

### `get_contact`

用途：

- 获取联系人信息

典型场景：

- 只想查联系人详情，不需要完整上下文

### `get_recent_messages`

用途：

- 获取最近消息

典型场景：

- 先看最近对话，再决定是否跟进

### `update_customer_tags`

用途：

- 给客户加标签或去标签

典型场景：

- 把客户标记成“待跟进”“已报名”“高意向”等

### `create_private_message_task`

用途：

- 创建私聊群发任务

典型场景：

- 针对单个客户或一批客户发私聊消息任务

### `create_group_message_task`

用途：

- 创建客户群群发任务

典型场景：

- 给客户群推送活动通知、直播提醒等

### `create_moment_task`

用途：

- 创建朋友圈任务

典型场景：

- 发朋友圈曝光或活动内容

### `get_hourly_followup_candidates`

用途：

- 获取本小时最该联系的候选客户

典型场景：

- 做每小时轮询和人工跟进排序

### `get_owner_recent_chat_dump`

用途：

- 拉某个员工最近聊天 dump

典型场景：

- 看某位员工最近私聊对话摘要或原始聊天转储

## 关键提醒

这些工具的逻辑都不在代理里。

代理只负责转发，所以：

- 工具是否存在，由远端 CRM 主服务决定
- 工具返回什么数据，也由远端 CRM 主服务决定
