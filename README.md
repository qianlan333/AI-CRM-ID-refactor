# AI-CRM

AI-CRM 是当前主线仓库，默认运行入口已经切到 AI-CRM Next FastAPI modular monolith。
旧 Flask 结构仍保留为 legacy fallback，方便回滚、对比和后续分批退场。

当前主线包含：

- AI-CRM Next modular monolith
- CRM 后台控制台
- 问卷与公众号 OAuth 流程
- 客户中心 / 客户时间线（AI-CRM Next 默认 owner；旧 Flask D3 readonly owner 已退场）
- 自动化转化配置与阶段看板
- OpenClaw / MCP 集成

## 当前主线口径

- GitHub `main` 是唯一源码主线。
- `python3 app.py run` 默认启动 AI-CRM Next。
- 旧 Flask 只能通过 `python3 app.py run-legacy` 或 `python3 legacy_flask_app.py run` 显式启动。
- 本地开发统一基于当前 Git clone，从最新 `main` 开功能分支。
- 仓库只保留源码、脚本、测试和文档，不再把发布包、导出物、临时备份和本机专属路径一起带进主仓。
- 生产 Nginx/systemd 切换仍需单独人工审批；本仓库入口切换不代表生产流量已经切换。

## 建议先读

- [docs/llm_handoff.md](docs/llm_handoff.md)
- [docs/project_map.md](docs/project_map.md)
- [docs/user_ops_v2.md](docs/user_ops_v2.md)
- [docs/deploy_runbook.md](docs/deploy_runbook.md)

如果任务偏 MCP / OpenClaw，再补：

- [docs/mcp_usage.md](docs/mcp_usage.md)
- [docs/openclaw_crm_read_contract.md](docs/openclaw_crm_read_contract.md)

如果任务偏自动化转化业务验收，再补：

- [docs/automation_conversion_acceptance_support_package.md](docs/automation_conversion_acceptance_support_package.md)
- [docs/automation_conversion_business_acceptance.md](docs/automation_conversion_business_acceptance.md)
- [docs/automation_conversion_local_runbook.md](docs/automation_conversion_local_runbook.md)

## 快速启动

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 app.py run
```

本地默认监听：

- `http://127.0.0.1:5001`，除非设置 `APP_PORT`

旧 Flask fallback：

```bash
python3 app.py run-legacy
python3 app.py init-db-legacy
```

兼容旧部署脚本的 `python3 app.py init-db` 仍保留为 legacy alias，但新文档应优先使用 `init-db-legacy`。

## 测试基线

root 全量测试的标准环境是安装了 `requirements.txt` 的虚拟环境，root pytest 只收集顶层 `tests/`。系统 Python 如果没有安装 FastAPI、SQLAlchemy、Alembic 等依赖，直接运行 `python3 -m pytest -q` 会在 collection 阶段失败，这不是代码回归。

推荐入口：

```bash
scripts/run_tests.sh
```

等价手动命令：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
```

AI-CRM Next experiment 目录仍保留独立测试环境，用于验证实验 docs/tools/tests 从 root `aicrm_next/` 导入：

```bash
cd experiments/ai_crm_next
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
```

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
  - 默认应用入口，`run` 启动 AI-CRM Next，legacy 命令显式启动旧 Flask
- `legacy_flask_app.py`
  - 旧 Flask fallback runner
- `aicrm_next/`
  - 当前默认 FastAPI modular monolith
- `wecom_ability_service/`
  - legacy Flask fallback
  - `http/` 负责路由与控制器
  - `domains/` 负责业务能力
  - Media/Product/Customer/User Ops/Questionnaire readonly legacy route owners 已按 D1-D5 分批退场，混合依赖包仅作 fallback/reference
  - `templates/admin_console/` 和 `static/admin_console/` 负责后台页面
- `openclaw_service/`
  - legacy OpenClaw 适配、工具和服务，默认不作为新功能入口
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

## Worktree 工作流

如果你要并行推进多个分支项目，建议直接用仓库自带脚本管理 worktree，不依赖 Codex 当前的创建工作树 UI。

先同步主线：

```bash
git switch main
git pull --ff-only
```

创建一个新的分支 worktree：

```bash
scripts/worktree-new.sh feature/customer-timeline
```

默认会在当前仓库旁边创建一个目录，命名规则类似：

```text
/Users/qianlan/Downloads/aicrm-new-feature-customer-timeline
```

如果你要指定基线或目录，也可以这样：

```bash
scripts/worktree-new.sh feature/customer-timeline origin/main /tmp/aicrm-customer-timeline
```

开发完成并合并后，移除 worktree：

```bash
scripts/worktree-remove.sh feature/customer-timeline
```

如果分支已经合并，也可以顺便删掉本地分支：

```bash
scripts/worktree-remove.sh feature/customer-timeline --delete-branch
```
