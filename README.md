# openclaw-private-conversion-console-v1

一个极简的 “OpenClaw 企微能力服务”。

当前只做 3 件事：

1. 通过企业微信官方会话存档 C SDK 拉取、解密、存储聊天记录
2. 调用企业微信官方接口创建私信群发 / 朋友圈 / 客户群群发任务
3. 调用企业微信官方标签能力

不做复杂后台，不做前端系统，不做 webhook，不做自动聊天，不做附件解析，不做权限系统。

## 当前状态

当前项目已经把企业微信官方会话存档 SDK 直接接进当前 Flask 单服务。

不再依赖假的 archive adapter，也不需要单独部署第二个 archive 服务。

## 文件树

```text
openclaw-private-conversion-console-v1/
├── README.md
├── app.py
├── requirements.txt
├── wecom_ability_service/
│   ├── __init__.py
│   ├── archive_adapter.py
│   ├── archive_sdk.py
│   ├── db.py
│   ├── routes.py
│   ├── schema.sql
│   ├── services.py
│   └── wecom_client.py
└── tests/
    └── test_api.py
```

## 官方会话存档接入说明

本项目使用企业微信官方会话存档 C SDK，并在当前服务内完成：

- `NewSdk`
- `Init`
- `GetChatData` 分页拉取
- `DecryptData` 解密
- 本地保存最大 `seq` 用于增量同步

当前第一版只保存单聊 `text` 消息。

## 真实环境约定

当前代码已经按下面路径做了默认值：

- `WECOM_PRIVATE_KEY_PATH=/home/ubuntu/wecom_private_key.pem`
- `WECOM_SDK_LIB_PATH=/home/ubuntu/wecom-sdk/C_sdk/libWeWorkFinanceSdk_C.so`

你当前服务器上的实际文件路径：

- SDK 动态库：
  `/home/ubuntu/wecom-sdk/C_sdk/libWeWorkFinanceSdk_C.so`
- SDK 头文件：
  `/home/ubuntu/wecom-sdk/C_sdk/WeWorkFinanceSdk_C.h`
- 私钥文件：
  `/home/ubuntu/wecom_private_key.pem`

## 配置项

### 必填

- `WECOM_CORP_ID`
- `WECOM_ARCHIVE_SECRET`
- `WECOM_PRIVATE_KEY_PATH`
- `WECOM_SDK_LIB_PATH`
- `WECOM_DEFAULT_OWNER_USERID`

### 群发 / 标签官方接口还会用到

- `WECOM_SECRET`
- `WECOM_AGENT_ID`
- `WECOM_API_BASE`

### 问卷 OAuth / 会话还会用到

- `SECRET_KEY`
- `WECHAT_MP_APP_ID`
- `WECHAT_MP_APP_SECRET`
- `WECHAT_MP_OAUTH_SCOPE`

默认：

- `WECHAT_MP_OAUTH_SCOPE=snsapi_base`

说明：

- 缺少这些配置不会阻塞服务启动
- 但微信内网页授权、会话写入 `openid/unionid` 会不可用
- 启动日志会明确提示哪些项缺失

默认：

- `WECOM_API_BASE=https://qyapi.weixin.qq.com`
- `WECOM_PRIVATE_KEY_PATH=/home/ubuntu/wecom_private_key.pem`
- `WECOM_SDK_LIB_PATH=/home/ubuntu/wecom-sdk/C_sdk/libWeWorkFinanceSdk_C.so`

## 数据表结构

### `archived_messages`

保存已解密并落库的文本消息：

- `id`
- `seq`
- `msgid`
- `external_userid`
- `owner_userid`
- `sender`
- `receiver`
- `msgtype`
- `content`
- `send_time`
- `raw_payload`
- `created_at`

索引：

- `msgid` 唯一索引
- `seq` 普通索引
- `(external_userid, send_time)` 复合索引
- `(owner_userid, send_time)` 复合索引

### `archive_sync_state`

保存官方会话存档增量位点：

- `state_key`
- `last_seq`
- `updated_at`

当前用固定键 `global` 保存全局最大 `seq`。

### `sync_runs`

记录每次同步过程：

- `id`
- `status`
- `start_time`
- `end_time`
- `owner_userid`
- `cursor`
- `fetched_count`
- `inserted_count`
- `raw_response`
- `error_message`
- `created_at`
- `finished_at`

### `outbound_tasks`

记录官方群发 / 朋友圈任务创建结果。

### `contact_tags`

记录本地标签操作快照。

### `app_settings`

保存 API 写入的运行配置。

## API 文档

OpenClaw 最小调用清单见：

- [`docs/openclaw_api.md`](/Users/qianlan/Downloads/极简%20crm/docs/openclaw_api.md)
- [`docs/mcp_usage.md`](/Users/qianlan/Downloads/极简%20crm/docs/mcp_usage.md)
- [`docs/postgresql_migration.md`](/Users/qianlan/Downloads/极简%20crm/docs/postgresql_migration.md)
- [`docs/questionnaire_e2e.md`](/Users/qianlan/Downloads/极简%20crm/docs/questionnaire_e2e.md)
- [`docs/questionnaire_oauth_go_live.md`](/Users/qianlan/Downloads/极简%20crm/docs/questionnaire_oauth_go_live.md)

## MCP 当前推荐用法

当前给 OpenClaw 的主 MCP 输入工具是：

- `get_owner_recent_chat_dump`

推荐流程：

1. `get_owner_recent_chat_dump(owner_userid, lookback_minutes=60)`
2. OpenClaw 自己判断谁最该联系
3. 对目标客户调用 `get_customer_context`
4. 如需要，再调用 `update_customer_tags`
5. 如需要，再调用任务工具

说明：

- MCP 只负责按顾问和时间窗返回聊天 dump
- MCP 不再负责输出“全局最该联系谁”
- `get_hourly_followup_candidates` 仍保留，但仅作旧兼容工具

### `GET /health`

服务健康检查。

示例响应：

```json
{
  "ok": true,
  "service": "openclaw-wecom-ability-service"
}
```

### `GET /api/archive/health`

检查会话存档 SDK 接入状态。

示例响应：

```json
{
  "ok": true,
  "adapter": {
    "ok": true,
    "mode": "official-sdk",
    "sdk_lib_path": "/home/ubuntu/wecom-sdk/C_sdk/libWeWorkFinanceSdk_C.so",
    "sdk_lib_exists": true,
    "private_key_path": "/home/ubuntu/wecom_private_key.pem",
    "private_key_exists": true
  }
}
```

### `POST /api/archive/sync`

真正调用官方会话存档 SDK 拉取、解密并入库。

请求示例：

```json
{
  "start_time": "2026-03-20 00:00:00",
  "end_time": "2026-03-20 23:59:59",
  "owner_userid": "sales_01"
}
```

响应示例：

```json
{
  "ok": true,
  "sync_run": {
    "id": 1,
    "status": "success",
    "fetched_count": 20,
    "inserted_count": 6,
    "has_more": false,
    "next_cursor": "5818",
    "last_seq": 5818
  }
}
```

说明：

- `cursor` 可选
- 传了 `cursor` 时，本次从指定 `seq` 开始拉
- 不传时，默认从 `archive_sync_state.last_seq` 继续增量同步
- 当前版本只保存单聊文本消息

### `GET /archive/messages?start_time=...&end_time=...&owner_userid=...&cursor=...`

读取本服务数据库里指定时间窗的已归档消息。

调用示例：

```bash
curl "http://127.0.0.1:5000/archive/messages?start_time=2026-03-20%2000:00:00&end_time=2026-03-20%2023:59:59&owner_userid=sales_01&cursor="
```

### `GET /api/messages/<external_userid>`

按客户读取全部历史消息。

### `GET /api/messages/search?external_userid=...&keyword=...`

按客户关键词搜索消息。

### `POST /api/tasks/private-message`

调用官方接口创建客户私信群发任务。

### `POST /api/tasks/moment`

调用官方接口创建客户朋友圈任务。

### `POST /api/tasks/group-message`

调用官方接口创建客户群群发任务。

### `GET /api/tags`

获取企业标签库。

### `POST /api/tags`

创建企业标签。

### `POST /api/tags/mark`

给客户打标签。

### `POST /api/tags/unmark`

给客户删标签。

### `GET /api/settings`

读取当前配置快照，敏感字段会遮挡。

### `PUT /api/settings`

写入配置项。

请求示例：

```json
{
  "settings": {
    "WECOM_CORP_ID": "wwxxxx",
    "WECOM_SECRET": "secret-value",
    "WECOM_AGENT_ID": "1000002",
    "WECOM_ARCHIVE_SECRET": "archive-secret",
    "WECOM_PRIVATE_KEY_PATH": "/home/ubuntu/wecom_private_key.pem",
    "WECOM_SDK_LIB_PATH": "/home/ubuntu/wecom-sdk/C_sdk/libWeWorkFinanceSdk_C.so",
    "WECOM_DEFAULT_OWNER_USERID": "sales_01"
  }
}
```

## 本地运行

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python app.py init-db
python app.py run
```

默认访问地址：

- `http://127.0.0.1:5000`

## Ubuntu 部署

只需要部署这一个服务。

### 1. 安装依赖

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

### 2. 部署项目

```bash
cd /opt
sudo mkdir -p openclaw-private-conversion-console-v1
sudo chown $USER:$USER openclaw-private-conversion-console-v1
cd openclaw-private-conversion-console-v1
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py init-db
```

### 3. 环境变量

```bash
export FLASK_ENV=production
export APP_HOST=0.0.0.0
export APP_PORT=5000
export DATABASE_PATH=/opt/openclaw-private-conversion-console-v1/data.sqlite3
export WECOM_CORP_ID=wwxxxx
export WECOM_SECRET=xxxx
export WECOM_AGENT_ID=1000002
export WECOM_ARCHIVE_SECRET=archive-secret
export WECOM_PRIVATE_KEY_PATH=/home/ubuntu/wecom_private_key.pem
export WECOM_SDK_LIB_PATH=/home/ubuntu/wecom-sdk/C_sdk/libWeWorkFinanceSdk_C.so
export WECOM_DEFAULT_OWNER_USERID=sales_01
```

### 4. 启动

```bash
source .venv/bin/activate
python app.py run
```

## 第一次真实同步怎么执行

第一次建议明确传一个时间窗，并从 `cursor=0` 开始：

```bash
curl -X POST http://127.0.0.1:5000/api/archive/sync \
  -H 'Content-Type: application/json' \
  -d '{
    "start_time": "2026-03-20 00:00:00",
    "end_time": "2026-03-20 23:59:59",
    "owner_userid": "sales_01",
    "cursor": "0"
  }'
```

后续增量同步可以不传 `cursor`：

```bash
curl -X POST http://127.0.0.1:5000/api/archive/sync \
  -H 'Content-Type: application/json' \
  -d '{
    "start_time": "2026-03-21 00:00:00",
    "end_time": "2026-03-21 23:59:59",
    "owner_userid": "sales_01"
  }'
```

## 我在服务器上还需要执行哪些命令

至少执行这些：

```bash
cd /opt/openclaw-private-conversion-console-v1
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python app.py init-db
python app.py run
```

如果要先确认路径存在：

```bash
ls -l /home/ubuntu/wecom-sdk/C_sdk/libWeWorkFinanceSdk_C.so
ls -l /home/ubuntu/wecom-sdk/C_sdk/WeWorkFinanceSdk_C.h
ls -l /home/ubuntu/wecom_private_key.pem
```

如果要先检查 archive 能力状态：

```bash
curl http://127.0.0.1:5000/api/archive/health
```

## 同步失败时优先看什么

按这个顺序排查最快：

1. `WECOM_SDK_LIB_PATH` 是否存在，且当前 Python 进程能加载 `.so`
2. `WECOM_PRIVATE_KEY_PATH` 是否存在，且私钥内容与企微后台公钥版本 `1` 对应
3. `WECOM_CORP_ID` 与 `WECOM_ARCHIVE_SECRET` 是否正确
4. 企业微信后台 “会话内容存档” 是否处于可试用或已开通状态
5. `GET /api/archive/health` 返回的 `sdk_lib_exists` / `private_key_exists` 是否为 `true`
6. 如果同步成功但没数据，优先看消息是否不是 `text`、是否不是单聊、是否不属于目标 `owner_userid`

## 风险与限制

- 当前 SDK 接入代码是基于官方 C SDK 常见函数签名实现的 Python `ctypes` 封装
- 当前第一版只支持 `publickey_ver=1`
- 当前只保存单聊文本消息
- 当前未处理图片、语音、文件、链接卡片、群聊解析
- 当前只做任务创建，不做任务结果轮询

## 说明

现在不需要 `WECOM_ARCHIVE_BASE_URL`。

当前部署只需要这一个 Flask 服务。
=======
# AI-CRM
>>>>>>> 52e1a0a0e3cdbc1d7c0ce51f4485f4d6b5a8e79f
