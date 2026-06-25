# SQL Authoring Guide

AI Audience SQL 只能查询 `audience_read.*` 白名单视图。SQL linter 会拒绝 DML/DDL、危险函数、非白名单依赖和 `SELECT *`。

## 允许视图

- `audience_read.identity_universe_v1`
- `audience_read.questionnaire_submissions_v1`
- `audience_read.orders_v1`
- `audience_read.wecom_contacts_v1`
- `audience_read.channel_entries_v1`

## 必填列

每条 SQL 必须输出：

- `identity_type`
- `identity_value`
- `event_source_key`
- `payload_json`

推荐同时输出：

- `external_userid`
- `event_at`

## 系统参数

系统会提供：

- `:last_watermark_at`
- `:refresh_started_at`
- `:lookback_seconds`
- `:package_id`

业务参数必须在 spec 的 `parameters` 中声明。

## 性能要求

增量 SQL 应限制在 watermark 和 refresh window 内；每日快照 SQL 应优先通过业务时间、状态和已加微关系收敛扫描范围。
