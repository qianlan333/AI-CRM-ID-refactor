# Markdown Package Spec

Spec 使用 YAML frontmatter 描述包配置，用 Markdown SQL block 描述版本 SQL。

````markdown
---
package_key: q101_submitted_added_wecom
name: 提交 101 问卷且已加微
status: paused
query_mode: incremental_event
identity_policy: external_userid
refresh_mode: incremental_3m
natural_language_definition: 提交了 101 问卷，且已经添加企业微信的用户。
parameters:
  questionnaire_id: 101
webhook:
  outbound_enabled: true
  outbound_webhook_url: https://agent.example.com/audience/entered
senders:
  - sender_userid: HuangYouCan
    display_name: HuangYouCan
    priority: 1
    status: active
---

# 业务说明

用于识别提交 101 问卷且已经加微的用户。

# Incremental SQL

```sql
SELECT
  'external_userid' AS identity_type,
  qs.external_userid AS identity_value,
  'questionnaire_submission:' || qs.submission_id::text AS event_source_key,
  jsonb_build_object('questionnaire_id', qs.questionnaire_id) AS payload_json,
  qs.external_userid,
  qs.submitted_at AS event_at
FROM audience_read.questionnaire_submissions_v1 qs
JOIN audience_read.wecom_contacts_v1 wc
  ON wc.external_userid = qs.external_userid
WHERE qs.questionnaire_id = :questionnaire_id
  AND qs.submitted_at >= :last_watermark_at - (:lookback_seconds || ' seconds')::interval
  AND qs.submitted_at < :refresh_started_at
```
````

## 必填 Frontmatter

- `package_key`
- `name`
- `refresh_mode`
- `natural_language_definition`

## Refresh Mode

只允许：

- `manual`
- `incremental_3m`
- `daily_0200`
- `incremental_3m_plus_daily_0200`

禁止 `incremental_5m`、5/15/30 分钟、cron、自定义时间。

## SQL 要求

- `incremental_3m` 必须有 `# Incremental SQL`。
- `daily_0200` 必须有 `# Snapshot SQL`。
- SQL 必须只查询 `audience_read.*` 白名单视图。
- 必须输出 `identity_type`、`identity_value`、`event_source_key`、`payload_json`。
- 推荐输出 `external_userid` 和 `event_at`。
- 禁止 `SELECT *`、DML/DDL、`public.*`、`pg_sleep`。
- 所有业务参数必须在 `parameters` 声明。

## 应用脚本

Dry-run 是默认行为：

```bash
python scripts/ai_audience_apply_package_spec.py docs/ai_audience/examples/questionnaire_submitted_added_wecom.md --dry-run
```

创建或更新但不发布：

```bash
python scripts/ai_audience_apply_package_spec.py docs/ai_audience/examples/questionnaire_submitted_added_wecom.md --apply
```

通过生产 Admin API 时必须显式确认：

```bash
AICRM_ADMIN_SESSION_COOKIE='...' \
python scripts/ai_audience_apply_package_spec.py docs/ai_audience/examples/questionnaire_submitted_added_wecom.md \
  --api-base https://www.youcangogogo.com \
  --admin-session-cookie-from-env \
  --apply \
  --confirm-production
```
