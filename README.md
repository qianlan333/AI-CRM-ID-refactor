# AI-CRM

AI-CRM 是当前主线仓库，承载这套 Flask 服务的源码、文档、脚本和测试。

当前主线包含：

- 企业微信能力服务
- CRM 后台控制台
- 问卷与公众号 OAuth 流程
- 客户中心 / 客户时间线
- 自动化转化配置与阶段看板
- OpenClaw / MCP 集成

## 当前主线口径

- GitHub `main` 是唯一源码主线。
- 本地开发统一基于当前 Git clone，从最新 `main` 开功能分支。
- 仓库只保留源码、脚本、测试和文档，不再把发布包、导出物、临时备份和本机专属路径一起带进主仓。

## 建议先读

- [docs/llm_handoff.md](docs/llm_handoff.md)
- [docs/project_map.md](docs/project_map.md)
- [docs/user_ops_v2.md](docs/user_ops_v2.md)
- [docs/deploy_runbook.md](docs/deploy_runbook.md)

如果任务偏 MCP / OpenClaw，再补：

- [docs/mcp_usage.md](docs/mcp_usage.md)
- [docs/openclaw_crm_read_contract.md](docs/openclaw_crm_read_contract.md)

## 快速启动

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 app.py init-db
python3 app.py run
```

本地默认监听：

- `http://127.0.0.1:5000`

## 生产环境快照

- 外网入口：`https://www.youcangogogo.com`
- systemd 服务：`openclaw-wecom-postgres.service`
- Nginx 上游：`http://127.0.0.1:5001`
- 生产代码目录：`/home/ubuntu/极简 crm`
- 环境变量文件：`/home/ubuntu/.openclaw-wecom-pg.env`
- 生产虚拟环境：`/home/ubuntu/venvs/openclaw/bin/activate`

更完整的发布与验收口径见：

- [docs/deploy_runbook.md](docs/deploy_runbook.md)

## 仓库结构

- `app.py`
  - 应用入口，支持 `init-db` 和 `run`
- `wecom_ability_service/`
  - 主 Flask 服务
  - `http/` 负责路由与控制器
  - `domains/` 负责业务能力
  - `templates/admin_console/` 和 `static/admin_console/` 负责后台页面
- `openclaw_service/`
  - OpenClaw 相关适配、工具和服务
- `docs/`
  - 项目说明、运行口径、接口和方案文档
- `scripts/`
  - 备份、迁移、校验、回填脚本
- `tests/`
  - 回归测试与契约测试
- `deploy/`
  - 生产 service 配置参考

## 开发约定

- 开始开发前先同步最新 `main`。
- 任何新功能都从当前 clone 的最新 `main` 开分支。
- 业务改动优先补测试，再提 PR。
- 部署时只以已经合入 `main` 的提交为准。
- `dist/`、`exports/`、顶层归档包、临时页面和本机调试产物不要再进主仓。
