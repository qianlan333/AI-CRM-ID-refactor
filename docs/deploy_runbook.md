# Deploy Runbook

这份文档描述当前项目最常用的本地与生产运行信息，方便 GPT / LLM 在回答部署和验收问题时有统一口径。

## 本地工作目录

- 本地主目录：
  - `/Users/qianlan/Downloads/极简 crm`

## 生产环境

当前主要生产实例：

- 服务名：`openclaw-wecom-postgres.service`
- 本机地址：`http://127.0.0.1:5001`
- 外网入口：`https://www.youcangogogo.com`

常用页面：

- 用户运营看板：
  - `https://www.youcangogogo.com/admin/user-ops/ui`
- 旧班期后台：
  - `https://www.youcangogogo.com/admin/class-user-backoffice/ui`
  - `https://www.youcangogogo.com/admin/class-user-management/ui`
- 问卷后台：
  - `https://www.youcangogogo.com/admin/questionnaires/ui`

## 生产代码目录

- `/home/ubuntu/极简 crm`

## 生产环境变量

- `/home/ubuntu/.openclaw-wecom-pg.env`

## 生产虚拟环境

- `/home/ubuntu/venvs/openclaw/bin/activate`

## 常用只读检查

服务健康：

- `curl -sS http://127.0.0.1:5001/health`

用户运营看板：

- `GET /api/admin/user-ops/overview`
- `GET /api/admin/user-ops/list`
- `GET /api/admin/user-ops/history`

MCP：

- `/mcp`

## 发布常见步骤

最常见的发布方式是：

1. 在本地改好代码
2. 本地做最小校验
3. 同步文件到 `/home/ubuntu/极简 crm`
4. 必要时执行数据库初始化 / 兼容迁移
5. 重启：
   - `openclaw-wecom-postgres.service`
6. 再做只读确认：
   - `/health`
   - 页面能打开
   - 关键 API 返回正常

## 数据库后端

当前项目支持：

- SQLite
- PostgreSQL

真实生产主线当前按 PostgreSQL 运行。

相关 schema 文件：

- [`wecom_ability_service/schema.sql`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service/schema.sql)
- [`wecom_ability_service/schema_postgres.sql`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service/schema_postgres.sql)

## 发布时最容易踩坑的地方

- PostgreSQL 和 SQLite 的 SQL 兼容差异
- 老库增量迁移顺序
- 页面缓存导致“线上明明已发布，本地浏览器仍看到旧模板”
- 企业微信真实标签和本地 `contact_tags` 快照不一致

## 如果模型要做真实环境验收

建议按这个顺序：

1. 先只读检查服务健康
2. 再检查页面 / API 是否在线
3. 再检查数据库表结构和当前池数据
4. 最后才做真实业务验收

不要一上来就对生产做写入动作。
