# 最终交付说明

## 1. 项目定位

### 服务解决的问题

这套服务是 OpenClaw 对接企业微信私域能力的底层支撑服务，目标是把“消息归档、客户映射、群目录、标签、官方群发任务、事件回调、自动增量同步”这些能力沉到一个稳定、可长期运行的后端里。

它不是 CRM，也不承载复杂前台页面。它解决的是：

- 把企业微信官方能力接成可调用 API
- 把聊天记录与客户映射沉淀到本地数据库
- 为 OpenClaw 后续的分析、检索、自动化动作提供稳定底座
- 提供最小可运维、可备份、可回滚的现网方案

### 当前版本名称

`OpenClaw × 企微底层稳定版 V1（PostgreSQL 现网已接管）`

## 2. 现网架构

- 域名：`https://www.youcangogogo.com`
- Nginx 配置路径：`/etc/nginx/sites-enabled/youcangogogo.conf`
- PostgreSQL 现网端口：`127.0.0.1:5001`
- SQLite 冷备端口：`127.0.0.1:5000`
- PostgreSQL systemd 服务名：`openclaw-wecom-postgres.service`
- PostgreSQL env 文件：`/home/ubuntu/.openclaw-wecom-pg.env`
- SQLite 冷备 env 文件：`/home/ubuntu/.openclaw-wecom.env`
- 项目路径：`/home/ubuntu/极简 crm`
- PostgreSQL 备份目录：`/home/ubuntu/backups/openclaw-postgres/`
- Nginx 日志：
  - `/var/log/nginx/access.log`
  - `/var/log/nginx/error.log`
- PostgreSQL 服务日志：
  - `sudo journalctl -u openclaw-wecom-postgres.service -f`
- cron 日志：
  - `/home/ubuntu/openclaw-cron.log`
  - `/home/ubuntu/openclaw-pg-backup.log`

### 当前 cron

增量同步：

```cron
*/5 * * * * /bin/bash -lc 'set -a && source /home/ubuntu/.openclaw-wecom-pg.env && set +a && source /home/ubuntu/venvs/openclaw/bin/activate && cd "/home/ubuntu/极简 crm" && python scripts/run_incremental_archive_sync.py >> /home/ubuntu/openclaw-cron.log 2>&1'
```

PostgreSQL 备份：

```cron
15 3 * * * /bin/bash -lc 'set -a && source /home/ubuntu/.openclaw-wecom-pg.env && set +a && cd "/home/ubuntu/极简 crm" && bash scripts/backup_postgres.sh >> /home/ubuntu/openclaw-pg-backup.log 2>&1'
```

## 3. 核心能力清单

### A. 会话存档

- 已接企业微信官方会话存档 C SDK
- 支持拉取、解密、入库文本消息
- 支持 `seq` 增量同步
- 支持私聊 / 群聊区分
- 支持按客户读取历史消息、最近消息、关键词搜索

### B. contacts 映射层

- 支持客户全量同步
- 支持客户增量同步
- 支持本地 contacts 映射表
- 支持自动补 description
- description 规则为纯 `external_userid`

### C. 群目录层

- 支持客户群全量同步
- 支持客户群增量同步
- 支持本地 `group_chats` 映射
- 消息结果可补 `chat_id` / `group_name`

### D. 标签能力

- 获取企业标签库
- 创建企业标签
- 给单个客户打标签
- 给单个客户删标签

### E. 官方任务能力

- 创建客户私信群发任务
- 创建客户朋友圈任务
- 创建客户群群发任务

### F. 自动回调 + 自动增量同步

- 已接企业微信“接收事件服务器”
- 支持 `msgaudit_notify`
- 回调采用“快回包、慢处理”
- 收到事件后自动触发增量 archive sync
- cron 每 5 分钟兜底补漏

### G. 运维状态接口

- 提供 `GET /api/ops/status`
- 可查看当前服务是否正常、消息数、联系人数、群数、最近同步状态、回调是否启用等

## 4. 核心 API 清单

### 消息

- `GET /api/messages/<external_userid>`
- `GET /api/messages/<external_userid>/recent?limit=N`
- `GET /api/messages/search?external_userid=...&keyword=...`
- `GET /api/archive/health`
- `POST /api/archive/sync`

### contacts

- `GET /api/contacts`
- `GET /api/contacts/<external_userid>`
- `POST /api/contacts/full-sync`
- `POST /api/contacts/sync-new`
- `POST /api/contacts/normalize-description`
- `POST /api/contacts/description`

### group_chats

- `POST /api/group-chats/full-sync`
- `POST /api/group-chats/sync-new`

### tags

- `GET /api/tags`
- `POST /api/tags`
- `POST /api/tags/mark`
- `POST /api/tags/unmark`

### tasks

- `POST /api/tasks/private-message`
- `POST /api/tasks/moment`
- `POST /api/tasks/group-message`

### ops

- `GET /health`
- `GET /api/ops/status`

### callback

- `GET /api/wecom/events`
- `POST /api/wecom/events`

## 5. 运维说明

### 启动

```bash
sudo systemctl start openclaw-wecom-postgres.service
```

### 重启

```bash
sudo systemctl restart openclaw-wecom-postgres.service
```

### 查看状态

```bash
sudo systemctl status openclaw-wecom-postgres.service --no-pager
curl -s http://127.0.0.1:5001/api/ops/status
```

### 查看日志

```bash
sudo journalctl -u openclaw-wecom-postgres.service -f
sudo tail -n 100 /var/log/nginx/access.log
sudo tail -n 100 /var/log/nginx/error.log
tail -n 100 /home/ubuntu/openclaw-cron.log
tail -n 100 /home/ubuntu/openclaw-pg-backup.log
```

### 手动跑 archive sync

```bash
curl -X POST http://127.0.0.1:5001/api/archive/sync \
  -H 'Content-Type: application/json' \
  -d '{
    "start_time": "2000-01-01 00:00:00",
    "end_time": "2099-12-31 23:59:59",
    "owner_userid": "QianLan",
    "cursor": ""
  }'
```

### 手动跑 contacts full-sync / sync-new

```bash
curl -X POST http://127.0.0.1:5001/api/contacts/full-sync
curl -X POST http://127.0.0.1:5001/api/contacts/sync-new
```

### 手动跑 group-chats full-sync / sync-new

```bash
curl -X POST http://127.0.0.1:5001/api/group-chats/full-sync
curl -X POST http://127.0.0.1:5001/api/group-chats/sync-new
```

## 6. 定时任务说明

### 增量同步 cron

- 每 5 分钟执行一次
- 作用：兜底拉取最新 archive 消息，补漏，不替代回调
- 日志：`/home/ubuntu/openclaw-cron.log`

### PostgreSQL 备份 cron

- 每天 `03:15` 执行一次
- 作用：生成 PostgreSQL dump 备份
- 备份目录：`/home/ubuntu/backups/openclaw-postgres/`
- 日志：`/home/ubuntu/openclaw-pg-backup.log`

## 7. 观察清单

### 每天看哪些接口

- `GET /api/ops/status`
- `GET /api/archive/health`
- 如需抽查，可补看：
  - `POST /api/contacts/sync-new`
  - `POST /api/group-chats/sync-new`

### 看哪些日志

- `sudo journalctl -u openclaw-wecom-postgres.service -f`
- `/var/log/nginx/access.log`
- `/var/log/nginx/error.log`
- `/home/ubuntu/openclaw-cron.log`
- `/home/ubuntu/openclaw-pg-backup.log`

### 看哪些关键字段

在 `GET /api/ops/status` 里重点看：

- `service_ok`
- `database_backend`
- `callback_enabled`
- `archived_messages_count`
- `contacts_count`
- `group_chats_count`
- `last_seq`
- `last_archive_sync_status`
- `last_archive_sync_time`

重点判断：

- `last_seq` 是否持续增长
- `last_archive_sync_status` 是否保持 `success`
- 消息总数是否在真实新消息到来后增长
- 回调是否仍然启用

## 8. 回滚说明

如果 PostgreSQL 现网出现异常，需要回滚到 SQLite 冷备：

1. 修改 Nginx 反代，把 `127.0.0.1:5001` 改回 `127.0.0.1:5000`

```bash
sudo sed -i 's#http://127.0.0.1:5001#http://127.0.0.1:5000#g' /etc/nginx/sites-enabled/youcangogogo.conf
sudo nginx -t
sudo systemctl reload nginx
```

2. 验证回滚后公网接口：

```bash
curl -s https://www.youcangogogo.com/health
curl -s https://www.youcangogogo.com/api/ops/status
```

3. SQLite 冷备说明

- SQLite 冷备服务端口：`127.0.0.1:5000`
- SQLite 冷备 env：`/home/ubuntu/.openclaw-wecom.env`
- SQLite 数据文件：`/home/ubuntu/极简 crm/data.sqlite3`

## 9. 安全提醒

以下密钥不要外传：

- `WECOM_SECRET`
- `WECOM_ARCHIVE_SECRET`
- `WECOM_CALLBACK_TOKEN`
- `WECOM_CALLBACK_AES_KEY`
- `DATABASE_URL` 中的数据库密码
- 企业微信私钥文件：`/home/ubuntu/wecom_private_key.pem`

以下值一旦暴露，应立即轮换：

- 企业微信应用 `Secret`
- 会话存档 `Secret`
- 回调 `Token`
- 回调 `EncodingAESKey`
- PostgreSQL 数据库密码

额外建议：

- 不要把 env 文件发到公开渠道
- 不要把备份 dump 发到聊天群
- 轮换密钥后要同步更新：
  - env 文件
  - PostgreSQL / SQLite `app_settings`
  - 企微后台回调配置
