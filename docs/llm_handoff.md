# LLM Handoff

这份文档给新模型或新同事一个最短入口。

## 先理解什么

先建立这 4 个事实：

- 这是当前唯一主线仓库
- GitHub `main` 是源码基线
- 默认 runtime 是 AI-CRM Next FastAPI modular monolith
- `app.py run` 默认启动 `aicrm_next.main:app`
- legacy Flask 只作为显式 fallback 和生产兼容 facade
- 当前项目不只是企微底层接口，还包含后台控制台、问卷、客户中心、自动化转化和 MCP 集成
- D9.6 后 `openclaw_service/` 和 `legacy_flask/openclaw_legacy/` 已物理删除，不是当前代码目录
- MCP/OpenClaw 后续只允许通过 `aicrm_next.integration_gateway` D7.7 adapter boundary 承接

## 如果模型能直接读仓库

建议按这个顺序读：

1. [README.md](../README.md)
2. [docs/project_map.md](project_map.md)
3. [docs/development/ai_crm_next_architecture_skill.md](development/ai_crm_next_architecture_skill.md)
4. [docs/user_ops_v2.md](user_ops_v2.md)
5. [docs/deploy_runbook.md](deploy_runbook.md)

然后再进入代码目录：

- [`aicrm_next/`](../aicrm_next)
- [`wecom_ability_service/`](../wecom_ability_service)
- [`tests/`](../tests)

## 如果模型不能直接读仓库

最稳的做法不是只给仓库链接，而是直接提供：

1. 这 5 份文档
2. `aicrm_next/`
3. `wecom_ability_service/`
4. `tests/`
5. 如任务和线上有关，再补当前服务名、上游端口、部署目录和环境变量文件路径

## 当前最值得优先理解的主线

- AI-CRM Next 默认 runtime 和 route ownership
- 企业微信能力服务
- CRM 后台控制台
- 问卷后台和公众号 OAuth
- 客户中心 / 客户时间线
- 自动化转化配置与阶段看板
- MCP / OpenClaw D7.7 adapter boundary（真实外呼仍 blocked / fake / staging-disabled）

## 建议阅读顺序

1. 先看文档，不要一上来扫全仓代码
2. 先用 [project_map.md](project_map.md) 建立目录边界
3. 再用 [deploy_runbook.md](deploy_runbook.md) 建立真实环境口径
4. 任务涉及用户运营或自动化转化时，再读 [user_ops_v2.md](user_ops_v2.md)
5. 最后进入具体代码和测试
