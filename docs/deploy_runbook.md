# Deploy Runbook

这份文档描述当前最常用的本地开发和生产发布口径。

当前代码默认运行入口已经切到 AI-CRM Next：

```bash
python3 app.py run
```

Legacy Flask startup compatibility 已关闭；不要再运行旧命令 `python3 app.py run-legacy` 或 `python3 legacy_flask_app.py run`。这些命令如出现在历史记录中，只代表迁移前口径，不是当前可执行入口。

这次入口变更本身不修改生产 Nginx/systemd，不代表生产流量已经切换。

## 本地仓库约定

- 当前 Git clone 就是本地唯一正式工作目录
- 新任务统一从最新 `main` 开分支
- 不再通过复制多个项目目录来并行开发

建议开始开发前先做：

```bash
git switch main
git pull --ff-only origin main
git switch -c <feature-branch>
```

## 生产环境

- 外网入口：`https://www.youcangogogo.com`
- systemd 服务：`openclaw-wecom-postgres.service`
- 商品支付外部推送 worker：`openclaw-external-push-worker.timer` / `openclaw-external-push-worker.service`
- Nginx 上游：`http://127.0.0.1:5001`
- 生产代码目录：`/home/ubuntu/极简 crm`
- 环境变量文件：`/home/ubuntu/.openclaw-wecom-pg.env`
- 生产虚拟环境：`/home/ubuntu/venvs/openclaw/bin/activate`

当前线上正式流量只走 `5001`。生产服务命令是否改为 Next 仍需单独人工审批。

不要再默认假设：

- 存在长期运行的 `5000` 冷备实例
- 服务器上存在多份并行有效的发布目录

## WeCom Callback Runtime Isolation

6 月 27 日 callback storm 后，目标架构把普通 Web 流量和企微回调流量拆成两个
runtime：

- `aicrm-web.service`：普通后台、sidebar、常规 API，监听 `127.0.0.1:5001`
- `aicrm-wecom-ingress.service`：企微 callback fast ACK ingress，监听 `127.0.0.1:5002`
- `aicrm-wecom-callback-worker.service`：消费 `webhook_inbox` 里的企微回调
- `aicrm-internal-event-worker.service`：消费 internal event backlog
- `aicrm-external-effect-worker.service`：消费 external effect jobs

仓库中同时保留当前生产兼容命名的 `openclaw-*` unit。不要在同一台生产机器上同时
enable 两套同职责 unit；切换到 canonical `aicrm-*` 命名需要单独审批，并先停掉对应
`openclaw-*` 兼容 unit/timer。

当前 GitHub deploy workflow 仍使用生产兼容命名安装并启动：

- `openclaw-wecom-postgres.service` 作为 5001 Web runtime
- `openclaw-wecom-callback-ingress.service` 作为 5002 callback ingress
- `openclaw-wecom-callback-inbox-worker.timer` 作为 callback worker dry-run 调度器

Callback worker unit 默认只预览 due rows，不会自动消费事故积压。需要小批量真实处理时，
先确认 dry-run 输出，再显式执行：

```bash
python scripts/run_wecom_callback_inbox_worker.py --limit 20
AICRM_WECOM_CALLBACK_INBOX_WORKER_EXECUTE=1 \
  python scripts/run_wecom_callback_inbox_worker.py --execute --limit 20
```

部署流程在启动 5002 callback ingress 和 callback worker timer 后会运行：

```bash
python scripts/ops/check_wecom_callback_deploy_smoke.py \
  | tee /tmp/wecom-callback-deploy-smoke.json
```

这个 smoke check 证明本机 `127.0.0.1:5001`、`127.0.0.1:5002` 可达，
`127.0.0.1:5002` 上的 `/wecom/external-contact/callback` 与
`/api/wecom/events` 都会用 app-level 4xx 拒绝无效 callback POST，并且
`/admin/webhook-inbox`、`/api/admin/webhook-inbox/metrics`、
`/api/admin/webhook-inbox/items`、`/api/admin/wecom/callback/reconciliation`
已经部署到 5001。JSON 产物会保存在
`/tmp/wecom-callback-deploy-smoke.json`，最终 readiness 必须通过
`--deploy-smoke-evidence-file` 消费它。它不证明公网 nginx 已从 quick ACK
切到 5002，也不替代压测、rollback drill、public-state 或最终 readiness 证据。
`--web-base-url` 和 `--ingress-base-url` 必须是不同地址；如果两者都传同一个
公网 URL，checker 会失败，因为这不能证明 5001/5002 已经隔离。

nginx 模板：

- `deploy/nginx-wecom-callback-ingress.conf.example`

该模板展示最终拓扑：

- `/` -> `aicrm_web` -> `127.0.0.1:5001`
- `/wecom/external-contact/callback` -> `aicrm_wecom_ingress` -> `127.0.0.1:5002`
- `/api/wecom/events` -> `aicrm_wecom_ingress` -> `127.0.0.1:5002`

不要直接覆盖生产 nginx server block；必须人工合并模板、执行 `nginx -t`，再运行：

```bash
cd /home/ubuntu/极简 crm
source /home/ubuntu/venvs/openclaw/bin/activate
set -a && source /home/ubuntu/.openclaw-wecom-pg.env && set +a
python scripts/ops/check_wecom_callback_ingress_cutover.py
python scripts/ops/check_wecom_callback_permanent_fix_readiness.py \
  --deploy-smoke-evidence-file /tmp/wecom-callback-deploy-smoke.json
```

`check_wecom_callback_permanent_fix_readiness.py` 没有压力测试、same-sample
ingestion/processing、worker isolation、downstream/internal-event isolation、rollback
证据时，必须保持 `ready_for_production_completion=false`。

## 常用只读检查

```bash
curl -sS http://127.0.0.1:5001/health
sudo systemctl status openclaw-wecom-postgres.service --no-pager
sudo journalctl -u openclaw-wecom-postgres.service -n 100 --no-pager
```

常用页面：

- `/admin`
- `/admin/customers`
- `/admin/questionnaires`
- `/admin/automation-conversion`
- `/admin/jobs`

## 发布口径

当前生产发布仍是手工同步，但源码基线统一来自 GitHub `main`。
GitHub Actions 里 `main` push 只跑关键路径 smoke，避免每个小 PR 合并后
都等待全量 PG 回归；完整 `full-test` 保留在 nightly 和手动触发。

AI-CRM Next 已经成为默认代码入口，但生产 route/systemd/Nginx 切换仍必须走人工签核。

推荐顺序：

1. 在本地最新 `main` 上开发和测试
2. 提交分支并合并到 GitHub `main`
3. 服务器部署时只同步已经合入 `main` 的代码
4. 同步到 `/home/ubuntu/极简 crm`
5. 必要时安装依赖并执行 Alembic schema migration
6. 确认本次是否已获批切换 systemd 命令
7. 重启 `openclaw-wecom-postgres.service`
8. 做只读验收

## 典型发布步骤

```bash
cd /home/ubuntu/极简\ crm
set -a
source /home/ubuntu/.openclaw-wecom-pg.env
set +a
test -n "${DATABASE_URL:-}"
source /home/ubuntu/venvs/openclaw/bin/activate
python3 -m pip install -r requirements.txt
# AI-CRM Next default runtime:
python3 app.py health

# AI-CRM Next schema migrations:
python3 -m alembic upgrade head
sudo systemctl restart openclaw-wecom-postgres.service
curl -sS http://127.0.0.1:5001/health
sudo cp deploy/openclaw-external-push-worker.service /etc/systemd/system/
sudo cp deploy/openclaw-external-push-worker.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable openclaw-external-push-worker.timer
sudo systemctl restart openclaw-external-push-worker.timer
sudo systemctl start openclaw-external-push-worker.service
sudo systemctl status openclaw-external-push-worker.timer --no-pager
```

不要在未经审批时修改生产 Nginx、systemd 或 route flag。不要把本地/staging evidence 写成 production canary 已执行。

## Runtime v2 真实发送验收队列隔离

Runtime v2 真实发送验收如果需要人工运行 broadcast worker，不能只检查
`systemctl --user`。服务器可能同时存在 root/system-level
`aicrm-broadcast-queue-worker.timer`，它会自动 claim due queued jobs，从而绕过人工
due queue guard。

验收前记录并检查两个层级：

```bash
systemctl --user status aicrm-broadcast-queue-worker.timer
systemctl --user status aicrm-broadcast-queue-worker.service
systemctl --user is-active aicrm-broadcast-queue-worker.timer
systemctl --user is-active aicrm-broadcast-queue-worker.service

systemctl status aicrm-broadcast-queue-worker.timer
systemctl status aicrm-broadcast-queue-worker.service
systemctl is-active aicrm-broadcast-queue-worker.timer
systemctl is-active aicrm-broadcast-queue-worker.service
```

若 user-level timer active，先执行：

```bash
systemctl --user stop aicrm-broadcast-queue-worker.timer
```

若 root/system-level timer active，先执行：

```bash
sudo systemctl stop aicrm-broadcast-queue-worker.timer
```

必须确认 user-level timer/service 与 root-level timer/service 都为 inactive 或不存在，才允许继续真实发送验收。

每次手动运行 worker `--limit 1` 前都必须执行 due queue guard：

```sql
SELECT id, source_type, source_id, channel, target_external_userids,
       content_payload, content_summary, scheduled_for, priority
FROM broadcast_jobs
WHERE status = 'queued' AND scheduled_for <= NOW()
ORDER BY priority ASC, scheduled_for ASC, id ASC
LIMIT 20;
```

旧 automation_runtime_v2 due job 已退场；生产验证应使用 AI Audience / external_effect_job 的当前链路，
`channel='wecom_private'`、目标只包含测试 external_userid、`content_payload.sender_userid`
等于预期 sender、`content_summary` 包含测试标识，才允许运行 worker。

验收后只恢复原来 active 的 timer：

```bash
# If the root/system-level timer was originally active:
sudo systemctl start aicrm-broadcast-queue-worker.timer

# If the user-level timer was originally active:
systemctl --user start aicrm-broadcast-queue-worker.timer
```

只恢复实际原来 active 的层级；恢复后确认 timer active，service 最终收敛为 inactive。

## 日志与备份

- service 日志：
  - `sudo journalctl -u openclaw-wecom-postgres.service -f`
- 自动化 due runner 日志：
  - `sudo journalctl -u openclaw-automation-conversion-due-runner.service -f`
  - `sudo systemctl status openclaw-automation-conversion-due-runner.timer --no-pager`
- 商品支付外部推送日志：
  - `sudo journalctl -u openclaw-external-push-worker.service -f`
  - `sudo systemctl status openclaw-external-push-worker.timer --no-pager`
- Nginx 日志：
  - `/var/log/nginx/access.log`
  - `/var/log/nginx/error.log`
- archive sync / backup 日志：
  - `/home/ubuntu/openclaw-cron.log`
  - `/home/ubuntu/openclaw-pg-backup.log`
- PostgreSQL 备份目录：
  - `/home/ubuntu/backups/openclaw-postgres/`

## 仓库与服务器清洁约定

- 服务器生产目录只保留一份正式代码
- smoke 目录、手工同步副本、历史发布包和 macOS 元数据不要长期堆在服务器
- 本地主仓不提交 `dist/`、`exports/`、顶层归档包、旧静态草稿页面

## 真实环境验收顺序

1. 先看服务和日志
2. 再看 `/health`
3. 再看关键页面和接口是否在线
4. 最后才做业务验收或写操作
