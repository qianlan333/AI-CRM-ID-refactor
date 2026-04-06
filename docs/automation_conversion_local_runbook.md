# 自动化转化本地联调 Runbook

## 1. 启动本地服务

```bash
cd /Users/qianlan/.codex/worktrees/8d7e/aicrm-new-codex-1
python3.11 -m venv .venv311-codex
source .venv311-codex/bin/activate
pip install -r requirements.txt
python app.py init-db
python app.py run
```

默认地址：

- `http://127.0.0.1:5000`

## 2. 配置本地环境项

推荐直接在后台设置页写入以下配置：

- `AUTOMATION_INTERNAL_API_TOKEN`
- `MCP_BEARER_TOKEN`（仅 legacy 兼容需要时保留）
- `OPENCLAW_FOCUS_MESSAGE_WEBHOOK_URL`
- `OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TOKEN`
- `OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TIMEOUT_SECONDS`
- `AUTOMATION_ACTIVATION_WEBHOOK_TOKEN`（仅 legacy 兼容需要时保留）
- `QUESTIONNAIRE_SUBMIT_WEBHOOK_URL`
- `QUESTIONNAIRE_SUBMIT_WEBHOOK_TOKEN`
- `QUESTIONNAIRE_SUBMIT_WEBHOOK_TIMEOUT_SECONDS`

如果只是本地联调，也可以在 app context 里直接写 `app_settings`：

```bash
python scripts/seed_automation_conversion_demo.py --write-settings \
  --internal-api-token internal-local-token \
  --mcp-token mcp-local-token \
  --openclaw-webhook-url http://127.0.0.1:19090/openclaw-focus \
  --openclaw-webhook-token focus-local-token \
  --activation-webhook-token activation-local-token \
  --questionnaire-webhook-url http://127.0.0.1:19090/questionnaire-submit \
  --questionnaire-webhook-token questionnaire-local-token
```

## 3. 启动本地 mock webhook

```bash
python - <<'PY'
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        size = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(size).decode()
        print(f"\\n== {self.path} ==")
        print(body)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

HTTPServer(("127.0.0.1", 19090), Handler).serve_forever()
PY
```

## 4. 准备测试问卷

1. 打开 `/admin/questionnaires`
2. 新建一份问卷
3. 至少准备：
   - 1 道单选或多选题
   - 1 道必填手机号题
4. 打开 `/admin/automation-conversion`
5. 选择这份问卷作为自动化转化问卷
6. 配置至少 1 道关键题
7. 配置普通跟进 / 重点跟进门槛
8. 配置 5 个池子的沉默阈值

## 5. 准备测试客户

运行 demo seed：

```bash
python scripts/seed_automation_conversion_demo.py
```

脚本会准备两个样本客户：

- `wm_demo_normal` / `13800138001` / `owner_userid=QianLan`
- `wm_demo_focus` / `13800138002` / `owner_userid=sales_demo_02`

## 6. 跑普通路径

1. 提交问卷：

```bash
curl -X POST http://127.0.0.1:5000/api/h5/questionnaires/<slug>/submit \
  -H 'Content-Type: application/json' \
  -d '{
    "external_userid":"wm_demo_normal",
    "answers":{
      "<问题id>":"<普通答案id>",
      "<手机号题id>":"13800138001"
    }
  }'
```

2. 验证当前仍在新用户池或等待试用开通：

```bash
curl -X POST http://127.0.0.1:5000/api/admin/marketing-automation/config/preview \
  -H 'Content-Type: application/json' \
  -d '{"external_userid":"wm_demo_normal"}'
```

3. 写入试用开通事实：

```bash
python scripts/seed_automation_conversion_demo.py --mark-trial-opened wm_demo_normal
```

4. 再次预览，确认进入 `pool/inactive_normal`

5. 回写激活：

```bash
curl -X POST http://127.0.0.1:5000/api/customers/automation/activation-webhook \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer internal-local-token' \
  -d '{"mobile":"13800138001","activated_at":"2026-04-06 10:10:00"}'
```

6. 再次预览，确认进入 `pool/active_normal`

## 7. 跑重点跟进路径

1. 提交问卷：

```bash
curl -X POST http://127.0.0.1:5000/api/h5/questionnaires/<slug>/submit \
  -H 'Content-Type: application/json' \
  -d '{
    "external_userid":"wm_demo_focus",
    "answers":{
      "<问题id>":"<命中重点跟进答案id>",
      "<手机号题id>":"13800138002"
    }
  }'
```

2. 写入试用开通事实：

```bash
python scripts/seed_automation_conversion_demo.py --mark-trial-opened wm_demo_focus
```

3. 预览确认进入 `pool/inactive_focus`

4. 验证重点跟进池来消息推送 OpenClaw：

```bash
python scripts/seed_automation_conversion_demo.py --insert-focus-message
```

预期本地 mock webhook 收到 `/openclaw-focus`。

5. 回写激活：

```bash
curl -X POST http://127.0.0.1:5000/api/customers/automation/activation-webhook \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer internal-local-token' \
  -d '{"mobile":"13800138002","activated_at":"2026-04-06 10:11:00"}'
```

6. 预览确认进入 `pool/active_focus`

## 8. 验证侧边栏人工改判

普通转重点：

```bash
curl -X POST http://127.0.0.1:5000/api/sidebar/marketing-status/set-followup-segment \
  -H 'Content-Type: application/json' \
  -d '{"external_userid":"wm_demo_normal","owner_userid":"QianLan","operator":"qa_local","followup_segment":"focus"}'
```

重点转普通：

```bash
curl -X POST http://127.0.0.1:5000/api/sidebar/marketing-status/set-followup-segment \
  -H 'Content-Type: application/json' \
  -d '{"external_userid":"wm_demo_focus","owner_userid":"sales_demo_02","operator":"qa_local","followup_segment":"normal"}'
```

然后查询状态：

```bash
curl "http://127.0.0.1:5000/api/sidebar/marketing-status?external_userid=wm_demo_focus"
```

## 9. 验证池子群发

```bash
curl -X POST http://127.0.0.1:5000/mcp \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer mcp-local-token' \
  -d '{
    "jsonrpc":"2.0",
    "id":1,
    "method":"tools/call",
    "params":{
      "name":"send_pool_private_message",
      "arguments":{
        "owner_userid":"sales_demo_02",
        "pool_key":"active_focus",
        "content":"这是本地联调群发消息",
        "confirm":true
      }
    }
  }'
```

纯图片：

```bash
curl -X POST http://127.0.0.1:5000/mcp \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer mcp-local-token' \
  -d '{
    "jsonrpc":"2.0",
    "id":2,
    "method":"tools/call",
    "params":{
      "name":"send_pool_private_message",
      "arguments":{
        "owner_userid":"sales_demo_02",
        "pool_key":"active_focus",
        "images":[{"file_name":"demo.png","data_url":"<data-url>"}],
        "confirm":true
      }
    }
  }'
```

文本 + 图片：

```bash
curl -X POST http://127.0.0.1:5000/mcp \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer mcp-local-token' \
  -d '{
    "jsonrpc":"2.0",
    "id":3,
    "method":"tools/call",
    "params":{
      "name":"send_pool_private_message",
      "arguments":{
        "owner_userid":"sales_demo_02",
        "pool_key":"active_focus",
        "content":"这是文本 + 图片联调消息",
        "images":[{"file_name":"demo.png","data_url":"<data-url>"}],
        "confirm":true
      }
    }
  }'
```

纯附件：

```bash
curl -X POST http://127.0.0.1:5000/mcp \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer mcp-local-token' \
  -d '{
    "jsonrpc":"2.0",
    "id":4,
    "method":"tools/call",
    "params":{
      "name":"send_pool_private_message",
      "arguments":{
        "owner_userid":"sales_demo_02",
        "pool_key":"active_focus",
        "attachments":[{"msgtype":"file","file":{"media_id":"file-media-001"}}],
        "confirm":true
      }
    }
  }'
```

文本 + 附件：

```bash
curl -X POST http://127.0.0.1:5000/mcp \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer mcp-local-token' \
  -d '{
    "jsonrpc":"2.0",
    "id":5,
    "method":"tools/call",
    "params":{
      "name":"send_pool_private_message",
      "arguments":{
        "owner_userid":"sales_demo_02",
        "pool_key":"active_focus",
        "content":"这是文本 + 附件联调消息",
        "attachments":[{"msgtype":"file","file":{"media_id":"file-media-002"}}],
        "confirm":true
      }
    }
  }'
```

文本 + 图片 + 附件：

```bash
curl -X POST http://127.0.0.1:5000/mcp \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer mcp-local-token' \
  -d '{
    "jsonrpc":"2.0",
    "id":6,
    "method":"tools/call",
    "params":{
      "name":"send_pool_private_message",
      "arguments":{
        "owner_userid":"sales_demo_02",
        "pool_key":"active_focus",
        "content":"这是文本 + 图片 + 附件联调消息",
        "images":[{"file_name":"demo.png","data_url":"<data-url>"}],
        "attachments":[{"msgtype":"file","file":{"media_id":"file-media-003"}}],
        "confirm":true
      }
    }
  }'
```

## 10. 验证沉默池不可群发

```bash
curl -X POST http://127.0.0.1:5000/mcp \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer mcp-local-token' \
  -d '{
    "jsonrpc":"2.0",
    "id":7,
    "method":"tools/call",
    "params":{
      "name":"send_pool_private_message",
      "arguments":{
        "owner_userid":"sales_demo_02",
        "pool_key":"silent",
        "content":"不应发送",
        "confirm":true
      }
    }
  }'
```

预期返回：

- `silent pool is record-only and does not support batch send`

## 11. 验证问卷提交外发 webhook

按第 6 步或第 7 步提交问卷后，检查本地 mock webhook 是否收到：

- `mobile`
- `userid`
- `unionid`

其中 `userid` 取 `questionnaire_submissions.follow_user_userid`。

## 12. 验证人工确认成交退出营销

```bash
curl -X POST http://127.0.0.1:5000/api/sidebar/marketing-status/mark-enrolled \
  -H 'Content-Type: application/json' \
  -d '{"external_userid":"wm_demo_focus","owner_userid":"sales_demo_02","operator":"qa_local"}'
```

再预览或查侧边栏状态，确认：

- `stage_key = converted/enrolled`
- `eligible_for_conversion = false`
