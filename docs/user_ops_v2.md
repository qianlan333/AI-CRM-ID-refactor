# User Ops V2

这份文档只描述用户运营看板 v2 当前已经落地的口径，不追溯历史讨论稿。

## 当前页面

- 页面地址：`/admin/user-ops/ui`
- 当前保留能力：
  - 当前状态池
  - 操作历史
  - `reload`
  - `export`
  - 班期回填
  - 自动归班任务执行

当前已下线的前端入口：

- 导入体验课手机号
- 导入激活黄小璨状态

说明：

- 这两个后端能力暂时仍保留
- 只是当前不再在 `user_ops` 页面里暴露对应按钮和弹窗

## 核心表

主表：

- `user_ops_pool_current`
- `user_ops_pool_history`
- `class_term_tag_mapping`
- `user_ops_deferred_jobs`

辅助来源：

- `contacts`
- `contact_tags`
- `external_contact_bindings`
- `people`
- `class_user_status_current`
- `owner_role_map`

## 当前状态池口径

`user_ops_pool_current` 是投影池，不是源数据真相。

它当前主要承载：

- `mobile`
- `external_userid`
- `customer_name`
- `owner_userid`
- `current_status`
- `is_wecom_bound`
- `activation_status`
- `activation_remark`
- `class_term_no`
- `class_term_label`

## 班期标签口径

班期逻辑当前已经收敛为：

- 班期定义来自企业微信真实客户标签字典
- 主匹配键是 `tag_id`
- `tag_name` 只用于展示和排查

使用的标签组：

- `9.9元改变计划`

当前已确认的班期映射包括：

- `1期` -> `首期7天改变计划`
- `3期` -> `0322改变计划-第3期`
- `4期` -> `0330改变计划-第4期`
- `5期` -> `第5期`
- `6期` -> `第6期`
- `7期` -> `第7期`
- `8期` -> `第8期`
- `9期` -> `第9期`
- `10期` -> `第10期`

## 标签读取口径

标签读取分两段：

1. 标签定义同步
   - 从企业微信客户标签字典同步到 `class_term_tag_mapping`
2. 客户当前标签刷新
   - 调企业微信客户详情
   - 刷新 `contact_tags`
   - 再按 `tag_id` 匹配

当前已经抽象出的通用能力是：

- 刷新客户全部标签
- 或只刷新指定范围的标签

这套逻辑同时服务于：

- user ops 的班期回填
- ZhaoYanFang 新用户自动归班
- MCP / OpenClaw 读取刷新后的标签

## ZhaoYanFang 当前已落地规则

当前最稳定、最明确的业务范围是 `owner_userid = ZhaoYanFang`。

已落地能力：

- 老用户班期回填
- 新用户延迟 10 秒自动归班
- 只对约定班期标签做班期判断

当前历史用户处理口径：

- 按企微客户处理
- 也就是基于已有 `external_userid` 的企业微信外部联系人

## 自动归班任务

最小任务表：

- `user_ops_deferred_jobs`

当前主要 job type：

- `auto_assign_class_term`

规则：

- 新用户进入 `ZhaoYanFang` 名下
- 延迟 10 秒
- 刷新该客户实时标签
- 单命中班期则写入
- 多命中则 `conflict`
- 无命中则 `skipped`

## 当前已知边界

- `contact_tags` 是本地快照，不是绝对真相
- 真正做班期判断前，必须先刷新实时标签
- 页面里的 `is_wecom_bound` 不等于“是否已加企微”
- 它更接近“是否已经挂上本地手机号绑定链路”

## 如果模型要继续开发 user ops v2

建议先读：

1. [`wecom_ability_service/templates/admin_user_ops.html`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service/templates/admin_user_ops.html)
2. [`wecom_ability_service/routes.py`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service/routes.py)
3. [`wecom_ability_service/services.py`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service/services.py)
4. [`tests/test_user_ops_api.py`](/Users/qianlan/Downloads/极简%20crm/tests/test_user_ops_api.py)
