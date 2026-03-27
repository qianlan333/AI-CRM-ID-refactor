# LLM Handoff

这份文档是给 GPT / LLM 的最小交接入口。

## 目标

让模型在最短时间内知道：

- 这个项目做什么
- 从哪里开始读
- 哪些模块是当前主线
- 哪些文档值得先看
- 私有仓库场景下，用户应该把什么内容给模型

## 如果模型可以直接读私有仓库

前提：

- 用户在 GPT / ChatGPT / 其他支持 GitHub 连接器的环境里，显式授权了仓库访问权限
- 仓库地址：`https://github.com/qianlan333/AI-CRM`

建议模型先读：

1. [`README.md`](/Users/qianlan/Downloads/极简%20crm/README.md)
2. [`docs/project_map.md`](/Users/qianlan/Downloads/极简%20crm/docs/project_map.md)
3. [`docs/user_ops_v2.md`](/Users/qianlan/Downloads/极简%20crm/docs/user_ops_v2.md)
4. [`docs/deploy_runbook.md`](/Users/qianlan/Downloads/极简%20crm/docs/deploy_runbook.md)

然后再进入代码目录：

- [`wecom_ability_service`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service)
- [`openclaw_service`](/Users/qianlan/Downloads/极简%20crm/openclaw_service)
- [`tests`](/Users/qianlan/Downloads/极简%20crm/tests)

## 如果模型不能直接读私有仓库

最稳的交付方式不是只给仓库链接，而是把下面这些内容直接提供给模型：

1. 这 4 份文档：
   - [`docs/llm_handoff.md`](/Users/qianlan/Downloads/极简%20crm/docs/llm_handoff.md)
   - [`docs/project_map.md`](/Users/qianlan/Downloads/极简%20crm/docs/project_map.md)
   - [`docs/user_ops_v2.md`](/Users/qianlan/Downloads/极简%20crm/docs/user_ops_v2.md)
   - [`docs/deploy_runbook.md`](/Users/qianlan/Downloads/极简%20crm/docs/deploy_runbook.md)
2. 核心代码目录压缩包或目录树：
   - [`wecom_ability_service`](/Users/qianlan/Downloads/极简%20crm/wecom_ability_service)
   - [`openclaw_service`](/Users/qianlan/Downloads/极简%20crm/openclaw_service)
   - [`tests`](/Users/qianlan/Downloads/极简%20crm/tests)
3. 如果任务和线上状态有关，再补当前环境信息：
   - 服务名：`openclaw-wecom-postgres.service`
   - 本机地址：`http://127.0.0.1:5001`
   - 外网入口：`https://www.youcangogogo.com`

## 当前主线能力

当前最值得优先理解的是这几条线：

- 企业微信能力服务：联系人、标签、回调、会话存档
- OpenClaw CRM / MCP 读写接口
- 用户运营看板 v2
- 问卷后台和相关 OAuth 流程
- 客户中心 / 客户时间线

## 当前最重要的业务口径

截至当前版本，用户运营看板 v2 的核心口径是：

- 历史用户主线按企微客户处理
- 班期匹配按 `tag_id`，不是只按 `tag_name`
- `ZhaoYanFang` 的班期逻辑是当前最主要的已落地范围
- 标签读取分成：
  - 标签定义字典同步
  - 客户当前标签刷新
- MCP 侧已经支持读取刷新后的标签

## 建议模型的阅读顺序

1. 先读文档，不要先扫全仓代码
2. 读 [`docs/project_map.md`](/Users/qianlan/Downloads/极简%20crm/docs/project_map.md) 了解目录和模块边界
3. 读 [`docs/user_ops_v2.md`](/Users/qianlan/Downloads/极简%20crm/docs/user_ops_v2.md) 了解用户运营看板当前规则
4. 读 [`docs/deploy_runbook.md`](/Users/qianlan/Downloads/极简%20crm/docs/deploy_runbook.md) 了解真实环境和发布方式
5. 最后再进代码实现
