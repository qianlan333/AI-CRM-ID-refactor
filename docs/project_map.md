# Project Map

这份文档是项目代码地图，目标是让新模型或新同事快速定位主模块。

## 顶层结构

```text
AI-CRM/
├── app.py
├── README.md
├── requirements.txt
├── docs/
├── scripts/
├── tests/
├── deploy/
├── openclaw_service/
└── wecom_ability_service/
```

## 入口

- [`app.py`](/Users/qianlan/Downloads/极简%20crm/app.py)
  - Flask 应用入口
- [`wecom_ability_service/__init__.py`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service/__init__.py)
  - 应用初始化、蓝图注册、配置接线

## `wecom_ability_service/`

这是当前项目最核心的业务服务目录，负责企业微信、用户运营、问卷、客户中心、MCP 暴露。

关键文件：

- [`wecom_ability_service/routes.py`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service/routes.py)
  - 主 HTTP 路由
  - 包括 admin UI、API、回调入口
- [`wecom_ability_service/services.py`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service/services.py)
  - 主要业务逻辑
  - 用户运营看板、标签刷新、班期逻辑、导入、投影池重建等都在这里
- [`wecom_ability_service/db.py`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service/db.py)
  - SQLite / PostgreSQL 双后端适配
  - 初始化和增量 schema 兼容逻辑
- [`wecom_ability_service/wecom_client.py`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service/wecom_client.py)
  - 企业微信 API 客户端
- [`wecom_ability_service/mcp_adapter.py`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service/mcp_adapter.py)
  - MCP 工具入口

子模块：

- [`wecom_ability_service/customer_center`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service/customer_center)
  - 客户中心聚合读接口
- [`wecom_ability_service/customer_timeline`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service/customer_timeline)
  - 客户时间线聚合
- [`wecom_ability_service/templates`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service/templates)
  - 后台页面模板
  - 当前用户运营看板页面在：
    - [`wecom_ability_service/templates/admin_user_ops.html`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service/templates/admin_user_ops.html)

## `openclaw_service/`

这是 OpenClaw 相关适配层，重点在 Feishu、CRM 工具、聊天上下文和工具注册。

关键目录：

- [`openclaw_service/feishu`](/Users/qianlan/Downloads/极简%20crm/openclaw_service/feishu)
  - 飞书 bot、命令、长连接
- [`openclaw_service/integrations/crm`](/Users/qianlan/Downloads/极简%20crm/openclaw_service/integrations/crm)
  - CRM 适配器、模型、认证、读写逻辑
- [`openclaw_service/tools`](/Users/qianlan/Downloads/极简%20crm/openclaw_service/tools)
  - OpenClaw 工具注册和业务工具
- [`openclaw_service/services`](/Users/qianlan/Downloads/极简%20crm/openclaw_service/services)
  - CRM operator、聊天上下文等服务

## `tests/`

按能力分布的测试集合。

当前和用户运营看板 / MCP 最相关的：

- [`tests/test_user_ops_api.py`](/Users/qianlan/Downloads/极简%20crm/tests/test_user_ops_api.py)
- [`tests/test_mcp_business_tools.py`](/Users/qianlan/Downloads/极简%20crm/tests/test_mcp_business_tools.py)
- [`tests/test_api.py`](/Users/qianlan/Downloads/极简%20crm/tests/test_api.py)

## `docs/`

当前项目文档比较多，但模型最值得先读的是：

- [`docs/llm_handoff.md`](/Users/qianlan/Downloads/极简%20crm/docs/llm_handoff.md)
- [`docs/project_map.md`](/Users/qianlan/Downloads/极简%20crm/docs/project_map.md)
- [`docs/user_ops_v2.md`](/Users/qianlan/Downloads/极简%20crm/docs/user_ops_v2.md)
- [`docs/deploy_runbook.md`](/Users/qianlan/Downloads/极简%20crm/docs/deploy_runbook.md)
- [`docs/mcp_usage.md`](/Users/qianlan/Downloads/极简%20crm/docs/mcp_usage.md)

## `deploy/`

- [`deploy/openclaw-wecom-postgres.service`](/Users/qianlan/Downloads/极简%20crm/deploy/openclaw-wecom-postgres.service)
  - 生产 service 配置参考

## `scripts/`

用于迁移、备份、验证和批处理。

关键脚本：

- [`scripts/migrate_sqlite_to_postgres.py`](/Users/qianlan/Downloads/极简%20crm/scripts/migrate_sqlite_to_postgres.py)
- [`scripts/backup_postgres.sh`](/Users/qianlan/Downloads/极简%20crm/scripts/backup_postgres.sh)
- [`scripts/openclaw_mcp_validation.mjs`](/Users/qianlan/Downloads/极简%20crm/scripts/openclaw_mcp_validation.mjs)

## 模型阅读建议

如果任务是：

- 理解后台页面和 API
  - 先看 [`wecom_ability_service/routes.py`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service/routes.py)
  - 再看 [`wecom_ability_service/services.py`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service/services.py)
- 理解 user ops v2
  - 先看 [`docs/user_ops_v2.md`](/Users/qianlan/Downloads/极简%20crm/docs/user_ops_v2.md)
  - 再看 [`tests/test_user_ops_api.py`](/Users/qianlan/Downloads/极简%20crm/tests/test_user_ops_api.py)
- 理解 MCP / OpenClaw
  - 先看 [`docs/mcp_usage.md`](/Users/qianlan/Downloads/极简%20crm/docs/mcp_usage.md)
  - 再看 [`wecom_ability_service/mcp_adapter.py`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service/mcp_adapter.py)
  - 再看 [`openclaw_service/tools`](/Users/qianlan/Downloads/极简%20crm/openclaw_service/tools)
