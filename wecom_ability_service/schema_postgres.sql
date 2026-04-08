CREATE TABLE IF NOT EXISTS archived_messages (
    id BIGSERIAL PRIMARY KEY,
    seq BIGINT,
    msgid TEXT NOT NULL UNIQUE,
    chat_type TEXT NOT NULL DEFAULT 'private',
    external_userid TEXT NOT NULL,
    owner_userid TEXT,
    sender TEXT NOT NULL,
    receiver TEXT,
    msgtype TEXT NOT NULL,
    content TEXT,
    send_time TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_archived_messages_external_send_time
ON archived_messages (external_userid, send_time);

CREATE INDEX IF NOT EXISTS idx_archived_messages_owner_send_time
ON archived_messages (owner_userid, send_time);

CREATE INDEX IF NOT EXISTS idx_archived_messages_seq
ON archived_messages (seq);

CREATE TABLE IF NOT EXISTS contacts (
    id BIGSERIAL PRIMARY KEY,
    external_userid TEXT NOT NULL UNIQUE,
    customer_name TEXT,
    owner_userid TEXT,
    remark TEXT,
    description TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_contacts_owner_userid
ON contacts (owner_userid);

CREATE TABLE IF NOT EXISTS people (
    id BIGSERIAL PRIMARY KEY,
    mobile TEXT NOT NULL UNIQUE,
    third_party_user_id TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS external_contact_bindings (
    external_userid TEXT PRIMARY KEY,
    person_id BIGINT NOT NULL REFERENCES people(id) ON DELETE RESTRICT,
    first_bound_by_userid TEXT NOT NULL DEFAULT '',
    first_owner_userid TEXT NOT NULL DEFAULT '',
    last_owner_userid TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_external_contact_bindings_person_id
ON external_contact_bindings (person_id);

CREATE TABLE IF NOT EXISTS group_chats (
    id BIGSERIAL PRIMARY KEY,
    chat_id TEXT NOT NULL UNIQUE,
    group_name TEXT,
    owner_userid TEXT,
    notice TEXT,
    member_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    create_time TEXT,
    dismissed_at TEXT,
    raw_payload TEXT NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_group_chats_owner_userid
ON group_chats (owner_userid);

CREATE INDEX IF NOT EXISTS idx_group_chats_status
ON group_chats (status);

CREATE TABLE IF NOT EXISTS sync_runs (
    id BIGSERIAL PRIMARY KEY,
    status TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    owner_userid TEXT,
    cursor TEXT,
    fetched_count INTEGER NOT NULL DEFAULT 0,
    inserted_count INTEGER NOT NULL DEFAULT 0,
    raw_response TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sync_runs_status_finished_at
ON sync_runs (status, finished_at);

CREATE TABLE IF NOT EXISTS outbound_tasks (
    id BIGSERIAL PRIMARY KEY,
    task_type TEXT NOT NULL,
    request_payload TEXT NOT NULL,
    response_payload TEXT NOT NULL,
    wecom_task_id TEXT,
    status TEXT NOT NULL DEFAULT 'created',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS outbound_webhook_deliveries (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    source_key TEXT NOT NULL DEFAULT '',
    source_id TEXT NOT NULL DEFAULT '',
    target_url TEXT NOT NULL DEFAULT '',
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload_summary TEXT NOT NULL DEFAULT '',
    token_configured BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    response_status_code INTEGER,
    response_body_summary TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    last_attempted_at TEXT NOT NULL DEFAULT '',
    next_retry_at TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_outbound_webhook_deliveries_event_created
ON outbound_webhook_deliveries (event_type, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_outbound_webhook_deliveries_status_created
ON outbound_webhook_deliveries (status, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_outbound_webhook_deliveries_next_retry
ON outbound_webhook_deliveries (next_retry_at, status);

CREATE TABLE IF NOT EXISTS contact_tags (
    id BIGSERIAL PRIMARY KEY,
    external_userid TEXT NOT NULL,
    userid TEXT NOT NULL,
    tag_id TEXT NOT NULL,
    tag_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (external_userid, userid, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_contact_tags_external_userid
ON contact_tags (external_userid);

CREATE TABLE IF NOT EXISTS owner_role_map (
    userid TEXT PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_owner_role_map_active
ON owner_role_map (active);

CREATE TABLE IF NOT EXISTS signup_tag_rules (
    tag_id TEXT PRIMARY KEY,
    tag_name TEXT NOT NULL DEFAULT '',
    signup_status TEXT NOT NULL DEFAULT '',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_signup_tag_rules_active
ON signup_tag_rules (active);

CREATE TABLE IF NOT EXISTS class_user_status_current (
    external_userid TEXT PRIMARY KEY,
    signup_status TEXT NOT NULL DEFAULT '',
    signup_label_name TEXT NOT NULL DEFAULT '',
    customer_name_snapshot TEXT NOT NULL DEFAULT '',
    owner_userid_snapshot TEXT NOT NULL DEFAULT '',
    mobile_snapshot TEXT NOT NULL DEFAULT '',
    set_by_userid TEXT NOT NULL DEFAULT '',
    set_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    wecom_tag_sync_status TEXT NOT NULL DEFAULT 'pending',
    wecom_tag_sync_error TEXT NOT NULL DEFAULT '',
    status_flags_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_class_user_status_current_signup_status
ON class_user_status_current (signup_status);

CREATE INDEX IF NOT EXISTS idx_class_user_status_current_set_at
ON class_user_status_current (set_at DESC);

CREATE TABLE IF NOT EXISTS class_user_status_history (
    id BIGSERIAL PRIMARY KEY,
    external_userid TEXT NOT NULL,
    old_signup_status TEXT NOT NULL DEFAULT '',
    new_signup_status TEXT NOT NULL DEFAULT '',
    old_label_name TEXT NOT NULL DEFAULT '',
    new_label_name TEXT NOT NULL DEFAULT '',
    customer_name_snapshot TEXT NOT NULL DEFAULT '',
    owner_userid_snapshot TEXT NOT NULL DEFAULT '',
    mobile_snapshot TEXT NOT NULL DEFAULT '',
    set_by_userid TEXT NOT NULL DEFAULT '',
    set_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    wecom_tag_sync_status TEXT NOT NULL DEFAULT 'pending',
    wecom_tag_sync_error TEXT NOT NULL DEFAULT '',
    status_flags_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_class_user_status_history_external_userid
ON class_user_status_history (external_userid, created_at DESC);

CREATE TABLE IF NOT EXISTS user_ops_pool_current (
    id BIGSERIAL PRIMARY KEY,
    mobile TEXT NOT NULL DEFAULT '',
    external_userid TEXT NOT NULL DEFAULT '',
    customer_name TEXT NOT NULL DEFAULT '',
    owner_userid TEXT NOT NULL DEFAULT '',
    current_status TEXT NOT NULL DEFAULT 'lead_trial',
    is_wecom_bound BOOLEAN NOT NULL DEFAULT FALSE,
    activation_status TEXT NOT NULL DEFAULT 'not_activated',
    activation_remark TEXT NOT NULL DEFAULT '',
    class_term_no INTEGER,
    class_term_label TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_ops_pool_current_status
ON user_ops_pool_current (current_status);

CREATE INDEX IF NOT EXISTS idx_user_ops_pool_current_bound
ON user_ops_pool_current (is_wecom_bound);

CREATE INDEX IF NOT EXISTS idx_user_ops_pool_current_activation
ON user_ops_pool_current (activation_status);

CREATE INDEX IF NOT EXISTS idx_user_ops_pool_current_class_term
ON user_ops_pool_current (class_term_no);

CREATE INDEX IF NOT EXISTS idx_user_ops_pool_current_owner
ON user_ops_pool_current (owner_userid);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_ops_pool_current_mobile_non_empty
ON user_ops_pool_current (mobile)
WHERE mobile <> '';

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_ops_pool_current_external_non_empty
ON user_ops_pool_current (external_userid)
WHERE external_userid <> '';

CREATE TABLE IF NOT EXISTS user_ops_do_not_disturb (
    id BIGSERIAL PRIMARY KEY,
    external_userid TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'manual',
    reason_code TEXT NOT NULL DEFAULT '',
    reason_text TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_ops_do_not_disturb_external_active
ON user_ops_do_not_disturb (external_userid, is_active, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_ops_do_not_disturb_mobile_active
ON user_ops_do_not_disturb (mobile, is_active, updated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_ops_do_not_disturb_external_reason
ON user_ops_do_not_disturb (external_userid, source_type, reason_code)
WHERE external_userid <> '';

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_ops_do_not_disturb_mobile_reason
ON user_ops_do_not_disturb (mobile, source_type, reason_code)
WHERE external_userid = '' AND mobile <> '';

CREATE TABLE IF NOT EXISTS user_ops_send_records (
    id BIGSERIAL PRIMARY KEY,
    task_type TEXT NOT NULL DEFAULT 'private_message',
    outbound_task_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    task_results_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    selected_count INTEGER NOT NULL DEFAULT 0,
    eligible_count INTEGER NOT NULL DEFAULT 0,
    sent_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    skipped_reasons_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    include_do_not_disturb BOOLEAN NOT NULL DEFAULT FALSE,
    content_preview TEXT NOT NULL DEFAULT '',
    image_count INTEGER NOT NULL DEFAULT 0,
    sender_userids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    filter_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    operator TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'created',
    last_status_sync_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_ops_send_records_created
ON user_ops_send_records (created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS user_ops_experience_leads (
    id BIGSERIAL PRIMARY KEY,
    mobile TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL DEFAULT 'experience_import',
    import_batch_id BIGINT,
    created_by TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_ops_experience_leads_active
ON user_ops_experience_leads (is_active);

CREATE TABLE IF NOT EXISTS user_ops_import_batches (
    id BIGSERIAL PRIMARY KEY,
    import_type TEXT NOT NULL DEFAULT '',
    file_name TEXT NOT NULL DEFAULT '',
    total_rows INTEGER NOT NULL DEFAULT 0,
    success_rows INTEGER NOT NULL DEFAULT 0,
    failed_rows INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_ops_import_batches_type_created
ON user_ops_import_batches (import_type, created_at DESC);

CREATE TABLE IF NOT EXISTS user_ops_activation_status_source (
    id BIGSERIAL PRIMARY KEY,
    mobile TEXT NOT NULL UNIQUE,
    activation_status TEXT NOT NULL DEFAULT 'not_activated'
        CHECK (activation_status IN ('not_activated', 'activated', 'high_intent')),
    activation_remark TEXT NOT NULL DEFAULT '',
    import_batch_id BIGINT,
    created_by TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_ops_activation_status_source_active
ON user_ops_activation_status_source (is_active);

CREATE TABLE IF NOT EXISTS user_ops_lead_pool_current (
    id BIGSERIAL PRIMARY KEY,
    mobile TEXT NOT NULL DEFAULT '',
    external_userid TEXT NOT NULL DEFAULT '',
    customer_name TEXT NOT NULL DEFAULT '',
    owner_userid TEXT NOT NULL DEFAULT '',
    is_wecom_added BOOLEAN NOT NULL DEFAULT FALSE,
    is_mobile_bound BOOLEAN NOT NULL DEFAULT FALSE,
    huangxiaocan_activation_state TEXT NOT NULL DEFAULT 'unknown'
        CHECK (huangxiaocan_activation_state IN ('unknown', 'activated', 'not_activated')),
    class_term_no INTEGER,
    class_term_label TEXT NOT NULL DEFAULT '',
    first_entry_source TEXT NOT NULL DEFAULT '',
    last_entry_source TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_ops_lead_pool_current_mobile_non_empty
ON user_ops_lead_pool_current (mobile)
WHERE mobile <> '';

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_ops_lead_pool_current_external_non_empty
ON user_ops_lead_pool_current (external_userid)
WHERE external_userid <> '';

CREATE INDEX IF NOT EXISTS idx_user_ops_lead_pool_current_wecom_added
ON user_ops_lead_pool_current (is_wecom_added);

CREATE INDEX IF NOT EXISTS idx_user_ops_lead_pool_current_mobile_bound
ON user_ops_lead_pool_current (is_mobile_bound);

CREATE INDEX IF NOT EXISTS idx_user_ops_lead_pool_current_activation
ON user_ops_lead_pool_current (huangxiaocan_activation_state);

CREATE TABLE IF NOT EXISTS user_ops_lead_pool_history (
    id BIGSERIAL PRIMARY KEY,
    mobile TEXT NOT NULL DEFAULT '',
    external_userid TEXT NOT NULL DEFAULT '',
    action_type TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT '',
    operator TEXT NOT NULL DEFAULT '',
    before_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    after_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    remark TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_ops_lead_pool_history_mobile
ON user_ops_lead_pool_history (mobile);

CREATE INDEX IF NOT EXISTS idx_user_ops_lead_pool_history_external
ON user_ops_lead_pool_history (external_userid);

CREATE INDEX IF NOT EXISTS idx_user_ops_lead_pool_history_created
ON user_ops_lead_pool_history (created_at DESC);

CREATE TABLE IF NOT EXISTS user_ops_huangxiaocan_activation_source (
    id BIGSERIAL PRIMARY KEY,
    mobile TEXT NOT NULL UNIQUE,
    activation_state TEXT NOT NULL
        CHECK (activation_state IN ('activated', 'not_activated')),
    import_batch_id TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_ops_huangxiaocan_activation_source_active
ON user_ops_huangxiaocan_activation_source (is_active);

CREATE TABLE IF NOT EXISTS user_ops_deferred_jobs (
    id BIGSERIAL PRIMARY KEY,
    job_type TEXT NOT NULL DEFAULT '',
    external_userid TEXT NOT NULL DEFAULT '',
    owner_userid TEXT NOT NULL DEFAULT '',
    run_after TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'success', 'skipped', 'conflict', 'failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_ops_deferred_jobs_status_run_after
ON user_ops_deferred_jobs (status, run_after);

CREATE INDEX IF NOT EXISTS idx_user_ops_deferred_jobs_owner_external
ON user_ops_deferred_jobs (owner_userid, external_userid);

CREATE TABLE IF NOT EXISTS user_ops_pool_history (
    id BIGSERIAL PRIMARY KEY,
    pool_id BIGINT,
    mobile TEXT NOT NULL DEFAULT '',
    external_userid TEXT NOT NULL DEFAULT '',
    action_type TEXT NOT NULL DEFAULT '',
    old_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    new_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    operator TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_ops_pool_history_pool_id
ON user_ops_pool_history (pool_id);

CREATE INDEX IF NOT EXISTS idx_user_ops_pool_history_mobile
ON user_ops_pool_history (mobile);

CREATE INDEX IF NOT EXISTS idx_user_ops_pool_history_external
ON user_ops_pool_history (external_userid);

CREATE INDEX IF NOT EXISTS idx_user_ops_pool_history_created
ON user_ops_pool_history (created_at DESC);

CREATE TABLE IF NOT EXISTS class_term_tag_mapping (
    id BIGSERIAL PRIMARY KEY,
    strategy_id TEXT NOT NULL DEFAULT '',
    group_id TEXT NOT NULL DEFAULT '',
    tag_id TEXT NOT NULL DEFAULT '',
    tag_group_name TEXT NOT NULL DEFAULT '',
    tag_name TEXT NOT NULL DEFAULT '',
    class_term_no INTEGER NOT NULL,
    class_term_label TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_class_term_tag_mapping_group_tag
ON class_term_tag_mapping (tag_group_name, tag_name);

CREATE UNIQUE INDEX IF NOT EXISTS uq_class_term_tag_mapping_tag_id_non_empty
ON class_term_tag_mapping (tag_id)
WHERE tag_id <> '';

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS routing_rule_config (
    rule_key TEXT PRIMARY KEY,
    routing_alias TEXT NOT NULL DEFAULT '',
    route_owner_userid TEXT NOT NULL DEFAULT '',
    route_owner_role TEXT NOT NULL DEFAULT '',
    routing_target TEXT NOT NULL DEFAULT '',
    fallback_target TEXT NOT NULL DEFAULT '',
    when_owner_role_sales TEXT NOT NULL DEFAULT '',
    when_owner_role_delivery TEXT NOT NULL DEFAULT '',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_routing_rule_config_active
ON routing_rule_config (active);

CREATE TABLE IF NOT EXISTS mcp_tool_settings (
    tool_name TEXT PRIMARY KEY,
    tool_group TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    description_override TEXT NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    visible_in_console BOOLEAN NOT NULL DEFAULT TRUE,
    show_sample_args BOOLEAN NOT NULL DEFAULT FALSE,
    show_sample_output BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mcp_tool_settings_enabled
ON mcp_tool_settings (enabled);

CREATE TABLE IF NOT EXISTS admin_operation_logs (
    id BIGSERIAL PRIMARY KEY,
    operator TEXT NOT NULL DEFAULT '',
    action_type TEXT NOT NULL DEFAULT '',
    target_type TEXT NOT NULL DEFAULT '',
    target_id TEXT NOT NULL DEFAULT '',
    before_json TEXT NOT NULL DEFAULT '{}',
    after_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_admin_operation_logs_target
ON admin_operation_logs (target_type, target_id, created_at DESC);

CREATE TABLE IF NOT EXISTS archive_sync_state (
    state_key TEXT PRIMARY KEY,
    last_seq BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS message_batches (
    id BIGSERIAL PRIMARY KEY,
    batch_key TEXT NOT NULL UNIQUE,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    message_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    acked_at TIMESTAMPTZ,
    ack_note TEXT,
    acked_by TEXT
);

ALTER TABLE message_batches
ADD COLUMN IF NOT EXISTS acked_by TEXT;

CREATE INDEX IF NOT EXISTS idx_message_batches_status_window
ON message_batches (status, window_start);

CREATE TABLE IF NOT EXISTS message_batch_items (
    id BIGSERIAL PRIMARY KEY,
    batch_id BIGINT NOT NULL REFERENCES message_batches(id) ON DELETE CASCADE,
    message_id BIGINT NOT NULL REFERENCES archived_messages(id) ON DELETE CASCADE,
    msgid TEXT NOT NULL,
    chat_type TEXT NOT NULL,
    chat_id TEXT,
    external_userid TEXT,
    owner_userid TEXT,
    send_time TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (message_id)
);

CREATE INDEX IF NOT EXISTS idx_message_batch_items_batch_id
ON message_batch_items (batch_id);

CREATE INDEX IF NOT EXISTS idx_message_batch_items_external_userid
ON message_batch_items (external_userid);

CREATE TABLE IF NOT EXISTS conversion_feedback (
    id BIGSERIAL PRIMARY KEY,
    external_userid TEXT,
    chat_id TEXT,
    feedback_type TEXT NOT NULL,
    feedback_payload TEXT NOT NULL DEFAULT '{}',
    actor TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS marketing_state_current (
    id BIGSERIAL PRIMARY KEY,
    scenario_key TEXT NOT NULL DEFAULT 'signup_conversion_v1',
    external_userid TEXT NOT NULL,
    marketing_phase TEXT NOT NULL DEFAULT 'awaiting_trigger',
    phase_label TEXT NOT NULL DEFAULT '',
    phase_reason TEXT NOT NULL DEFAULT '',
    lifecycle_status TEXT NOT NULL DEFAULT 'idle',
    last_batch_id BIGINT,
    last_batch_status TEXT NOT NULL DEFAULT '',
    last_batch_window_start TEXT NOT NULL DEFAULT '',
    last_batch_window_end TEXT NOT NULL DEFAULT '',
    last_trigger_message_at TEXT NOT NULL DEFAULT '',
    entered_at TIMESTAMPTZ,
    exited_at TIMESTAMPTZ,
    exit_reason TEXT NOT NULL DEFAULT '',
    source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (scenario_key, external_userid)
);

CREATE INDEX IF NOT EXISTS idx_marketing_state_current_phase
ON marketing_state_current (scenario_key, marketing_phase, lifecycle_status);

CREATE INDEX IF NOT EXISTS idx_marketing_state_current_external
ON marketing_state_current (external_userid, scenario_key);

CREATE TABLE IF NOT EXISTS marketing_value_segment_current (
    id BIGSERIAL PRIMARY KEY,
    scenario_key TEXT NOT NULL DEFAULT 'signup_conversion_v1',
    external_userid TEXT NOT NULL,
    value_segment TEXT NOT NULL DEFAULT 'normal',
    segment_label TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    score_breakdown_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (scenario_key, external_userid)
);

CREATE INDEX IF NOT EXISTS idx_marketing_value_segment_current_segment
ON marketing_value_segment_current (scenario_key, value_segment, score DESC);

CREATE INDEX IF NOT EXISTS idx_marketing_value_segment_current_external
ON marketing_value_segment_current (external_userid, scenario_key);

CREATE TABLE IF NOT EXISTS marketing_automation_configs (
    id BIGSERIAL PRIMARY KEY,
    automation_key TEXT NOT NULL UNIQUE,
    automation_name TEXT NOT NULL DEFAULT '',
    target_event TEXT NOT NULL DEFAULT 'signup_success',
    channel_type TEXT NOT NULL DEFAULT 'text_message',
    status TEXT NOT NULL DEFAULT 'active',
    do_not_start_after_hour INTEGER NOT NULL DEFAULT 23,
    config_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_marketing_automation_configs_status
ON marketing_automation_configs (status);

CREATE TABLE IF NOT EXISTS marketing_automation_question_rules (
    id BIGSERIAL PRIMARY KEY,
    automation_config_id BIGINT NOT NULL REFERENCES marketing_automation_configs(id) ON DELETE CASCADE,
    questionnaire_id BIGINT,
    question_id BIGINT,
    rule_code TEXT NOT NULL DEFAULT '',
    rule_name TEXT NOT NULL DEFAULT '',
    answer_match_type TEXT NOT NULL DEFAULT 'any_of',
    answer_match_value_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    score_delta INTEGER NOT NULL DEFAULT 0,
    segment_hint TEXT NOT NULL DEFAULT '',
    stage_hint TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    rule_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (automation_config_id, question_id, rule_code)
);

CREATE INDEX IF NOT EXISTS idx_marketing_automation_question_rules_config
ON marketing_automation_question_rules (automation_config_id, is_active, sort_order, id);

CREATE INDEX IF NOT EXISTS idx_marketing_automation_question_rules_question
ON marketing_automation_question_rules (question_id);

CREATE TABLE IF NOT EXISTS customer_value_segment_current (
    id BIGSERIAL PRIMARY KEY,
    external_userid TEXT NOT NULL UNIQUE,
    segment TEXT NOT NULL DEFAULT 'normal',
    segment_rank INTEGER NOT NULL DEFAULT 0,
    score INTEGER NOT NULL DEFAULT 0,
    scoring_version TEXT NOT NULL DEFAULT '',
    computed_reason TEXT NOT NULL DEFAULT '',
    submission_id BIGINT REFERENCES questionnaire_submissions(id) ON DELETE SET NULL,
    matched_question_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_customer_value_segment_current_external_userid
ON customer_value_segment_current (external_userid);

CREATE INDEX IF NOT EXISTS idx_customer_value_segment_current_segment
ON customer_value_segment_current (segment);

CREATE TABLE IF NOT EXISTS customer_value_segment_history (
    id BIGSERIAL PRIMARY KEY,
    external_userid TEXT NOT NULL,
    segment TEXT NOT NULL DEFAULT 'normal',
    segment_rank INTEGER NOT NULL DEFAULT 0,
    score INTEGER NOT NULL DEFAULT 0,
    scoring_version TEXT NOT NULL DEFAULT '',
    change_reason TEXT NOT NULL DEFAULT '',
    submission_id BIGINT REFERENCES questionnaire_submissions(id) ON DELETE SET NULL,
    matched_question_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_customer_value_segment_history_external_userid
ON customer_value_segment_history (external_userid, recorded_at DESC);

CREATE TABLE IF NOT EXISTS customer_marketing_state_current (
    id BIGSERIAL PRIMARY KEY,
    person_id BIGINT REFERENCES people(id) ON DELETE SET NULL,
    external_userid TEXT NOT NULL DEFAULT '',
    automation_key TEXT NOT NULL DEFAULT 'signup_conversion_v1',
    main_stage TEXT NOT NULL DEFAULT 'pending',
    sub_stage TEXT NOT NULL DEFAULT '',
    activated BOOLEAN NOT NULL DEFAULT FALSE,
    converted BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_conversion BOOLEAN NOT NULL DEFAULT FALSE,
    lifecycle_status TEXT NOT NULL DEFAULT 'idle',
    last_activation_at TEXT NOT NULL DEFAULT '',
    last_conversion_marked_at TEXT NOT NULL DEFAULT '',
    last_message_at TEXT NOT NULL DEFAULT '',
    last_batch_id BIGINT REFERENCES message_batches(id) ON DELETE SET NULL,
    last_batch_status TEXT NOT NULL DEFAULT '',
    last_batch_window_start TEXT NOT NULL DEFAULT '',
    last_batch_window_end TEXT NOT NULL DEFAULT '',
    last_trigger_message_at TEXT NOT NULL DEFAULT '',
    entered_at TIMESTAMPTZ,
    exited_at TIMESTAMPTZ,
    exit_reason TEXT NOT NULL DEFAULT '',
    state_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_current_external_userid
ON customer_marketing_state_current (external_userid);

CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_marketing_state_current_person_id_non_null
ON customer_marketing_state_current (person_id)
WHERE person_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_current_main_stage
ON customer_marketing_state_current (main_stage);

CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_current_sub_stage
ON customer_marketing_state_current (sub_stage);

CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_current_eligible_for_conversion
ON customer_marketing_state_current (eligible_for_conversion);

CREATE TABLE IF NOT EXISTS customer_marketing_state_history (
    id BIGSERIAL PRIMARY KEY,
    person_id BIGINT REFERENCES people(id) ON DELETE SET NULL,
    external_userid TEXT NOT NULL DEFAULT '',
    automation_key TEXT NOT NULL DEFAULT 'signup_conversion_v1',
    main_stage TEXT NOT NULL DEFAULT 'pending',
    sub_stage TEXT NOT NULL DEFAULT '',
    activated BOOLEAN NOT NULL DEFAULT FALSE,
    converted BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_conversion BOOLEAN NOT NULL DEFAULT FALSE,
    batch_id BIGINT REFERENCES message_batches(id) ON DELETE SET NULL,
    lifecycle_status TEXT NOT NULL DEFAULT 'idle',
    exit_reason TEXT NOT NULL DEFAULT '',
    last_activation_at TEXT NOT NULL DEFAULT '',
    last_conversion_marked_at TEXT NOT NULL DEFAULT '',
    last_message_at TEXT NOT NULL DEFAULT '',
    change_reason TEXT NOT NULL DEFAULT '',
    state_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_history_external_userid
ON customer_marketing_state_history (external_userid, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_history_person_id
ON customer_marketing_state_history (person_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS conversion_dispatch_log (
    id BIGSERIAL PRIMARY KEY,
    automation_key TEXT NOT NULL DEFAULT 'signup_conversion_v1',
    batch_id BIGINT NOT NULL REFERENCES message_batches(id) ON DELETE CASCADE,
    external_userid TEXT NOT NULL,
    dispatch_status TEXT NOT NULL DEFAULT 'pending',
    dispatch_channel TEXT NOT NULL DEFAULT 'text_message',
    dispatch_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    dispatch_note TEXT NOT NULL DEFAULT '',
    dispatched_at TIMESTAMPTZ,
    acked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (batch_id, external_userid)
);

CREATE INDEX IF NOT EXISTS idx_conversion_dispatch_log_batch_id
ON conversion_dispatch_log (batch_id);

CREATE INDEX IF NOT EXISTS idx_conversion_dispatch_log_external_userid
ON conversion_dispatch_log (external_userid);

CREATE INDEX IF NOT EXISTS idx_conversion_dispatch_log_dispatch_status
ON conversion_dispatch_log (dispatch_status);

CREATE TABLE IF NOT EXISTS wecom_external_contact_identity_map (
    id BIGSERIAL PRIMARY KEY,
    corp_id VARCHAR(64) NOT NULL,
    external_userid VARCHAR(128) NOT NULL,
    unionid VARCHAR(128) NOT NULL DEFAULT '',
    openid VARCHAR(128) NOT NULL DEFAULT '',
    follow_user_userid VARCHAR(128) NOT NULL DEFAULT '',
    name VARCHAR(255) NOT NULL DEFAULT '',
    type INTEGER,
    avatar TEXT NOT NULL DEFAULT '',
    gender INTEGER,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    raw_profile JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (corp_id, external_userid)
);

CREATE INDEX IF NOT EXISTS idx_identity_map_unionid
ON wecom_external_contact_identity_map (unionid);

CREATE INDEX IF NOT EXISTS idx_identity_map_openid
ON wecom_external_contact_identity_map (openid);

CREATE INDEX IF NOT EXISTS idx_identity_map_follow_user
ON wecom_external_contact_identity_map (follow_user_userid);

CREATE INDEX IF NOT EXISTS idx_identity_map_status
ON wecom_external_contact_identity_map (status);

CREATE TABLE IF NOT EXISTS wecom_external_contact_follow_users (
    id BIGSERIAL PRIMARY KEY,
    corp_id VARCHAR(64) NOT NULL,
    external_userid VARCHAR(128) NOT NULL,
    user_id VARCHAR(128) NOT NULL,
    relation_status VARCHAR(32) NOT NULL DEFAULT 'active',
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    remark TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    add_way INTEGER,
    state TEXT NOT NULL DEFAULT '',
    oper_userid VARCHAR(128) NOT NULL DEFAULT '',
    createtime BIGINT,
    raw_follow_user JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (corp_id, external_userid, user_id)
);

CREATE INDEX IF NOT EXISTS idx_external_contact_follow_users_external
ON wecom_external_contact_follow_users (corp_id, external_userid);

CREATE INDEX IF NOT EXISTS idx_external_contact_follow_users_user
ON wecom_external_contact_follow_users (user_id);

CREATE INDEX IF NOT EXISTS idx_external_contact_follow_users_status
ON wecom_external_contact_follow_users (relation_status);

CREATE TABLE IF NOT EXISTS wecom_external_contact_event_logs (
    id BIGSERIAL PRIMARY KEY,
    corp_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    change_type VARCHAR(64) NOT NULL,
    external_userid VARCHAR(128) NOT NULL DEFAULT '',
    user_id VARCHAR(128) NOT NULL DEFAULT '',
    event_time BIGINT,
    event_key VARCHAR(255) NOT NULL,
    payload_xml TEXT NOT NULL DEFAULT '',
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    process_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (event_key)
);

CREATE INDEX IF NOT EXISTS idx_external_contact_event_logs_status
ON wecom_external_contact_event_logs (process_status, updated_at);

CREATE TABLE IF NOT EXISTS questionnaires (
    id BIGSERIAL PRIMARY KEY,
    slug VARCHAR(128) NOT NULL UNIQUE,
    name TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_disabled BOOLEAN NOT NULL DEFAULT FALSE,
    redirect_url TEXT NOT NULL DEFAULT '',
    external_push_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    external_push_url TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_questionnaires_slug
ON questionnaires (slug);

CREATE INDEX IF NOT EXISTS idx_questionnaires_disabled
ON questionnaires (is_disabled);

CREATE INDEX IF NOT EXISTS idx_questionnaires_external_push_enabled
ON questionnaires (external_push_enabled);

CREATE TABLE IF NOT EXISTS questionnaire_questions (
    id BIGSERIAL PRIMARY KEY,
    questionnaire_id BIGINT NOT NULL REFERENCES questionnaires(id) ON DELETE CASCADE,
    type VARCHAR(32) NOT NULL CHECK (type IN ('single_choice', 'multi_choice', 'textarea', 'mobile')),
    title TEXT NOT NULL,
    required BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_questionnaire_questions_questionnaire
ON questionnaire_questions (questionnaire_id, sort_order, id);

CREATE TABLE IF NOT EXISTS questionnaire_options (
    id BIGSERIAL PRIMARY KEY,
    question_id BIGINT NOT NULL REFERENCES questionnaire_questions(id) ON DELETE CASCADE,
    option_text TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL DEFAULT 0,
    tag_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_questionnaire_options_question
ON questionnaire_options (question_id, sort_order, id);

CREATE TABLE IF NOT EXISTS questionnaire_score_rules (
    id BIGSERIAL PRIMARY KEY,
    questionnaire_id BIGINT NOT NULL REFERENCES questionnaires(id) ON DELETE CASCADE,
    min_score DOUBLE PRECISION,
    max_score DOUBLE PRECISION,
    tag_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_questionnaire_score_rules_questionnaire
ON questionnaire_score_rules (questionnaire_id, sort_order, id);

CREATE TABLE IF NOT EXISTS questionnaire_submissions (
    id BIGSERIAL PRIMARY KEY,
    questionnaire_id BIGINT NOT NULL REFERENCES questionnaires(id) ON DELETE CASCADE,
    identity_map_id BIGINT REFERENCES wecom_external_contact_identity_map(id) ON DELETE SET NULL,
    respondent_key TEXT NOT NULL DEFAULT '',
    openid TEXT NOT NULL DEFAULT '',
    unionid TEXT NOT NULL DEFAULT '',
    external_userid TEXT NOT NULL DEFAULT '',
    follow_user_userid TEXT NOT NULL DEFAULT '',
    matched_by VARCHAR(32) NOT NULL DEFAULT '',
    mobile_snapshot TEXT NOT NULL DEFAULT '',
    source_channel TEXT NOT NULL DEFAULT '',
    campaign_id TEXT NOT NULL DEFAULT '',
    staff_id TEXT NOT NULL DEFAULT '',
    total_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    final_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    redirect_url_snapshot TEXT NOT NULL DEFAULT '',
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_questionnaire_submissions_questionnaire
ON questionnaire_submissions (questionnaire_id, submitted_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_questionnaire_submissions_identity_map
ON questionnaire_submissions (identity_map_id);

CREATE INDEX IF NOT EXISTS idx_questionnaire_submissions_external
ON questionnaire_submissions (external_userid);

CREATE TABLE IF NOT EXISTS questionnaire_submission_answers (
    id BIGSERIAL PRIMARY KEY,
    submission_id BIGINT NOT NULL REFERENCES questionnaire_submissions(id) ON DELETE CASCADE,
    question_id BIGINT NOT NULL,
    question_type VARCHAR(32) NOT NULL,
    question_title_snapshot TEXT NOT NULL,
    selected_option_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    selected_option_texts_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
    selected_option_scores_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
    selected_option_tags_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
    text_value TEXT NOT NULL DEFAULT '',
    score_contribution DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_questionnaire_submission_answers_submission
ON questionnaire_submission_answers (submission_id, id);

CREATE INDEX IF NOT EXISTS idx_questionnaire_submission_answers_question
ON questionnaire_submission_answers (question_id);

CREATE TABLE IF NOT EXISTS questionnaire_scrm_apply_logs (
    id BIGSERIAL PRIMARY KEY,
    submission_id BIGINT NOT NULL REFERENCES questionnaire_submissions(id) ON DELETE CASCADE,
    external_userid TEXT NOT NULL DEFAULT '',
    follow_user_userid TEXT NOT NULL DEFAULT '',
    final_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'skipped',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_questionnaire_scrm_apply_logs_submission
ON questionnaire_scrm_apply_logs (submission_id, id);

CREATE INDEX IF NOT EXISTS idx_questionnaire_scrm_apply_logs_status
ON questionnaire_scrm_apply_logs (status, created_at);

CREATE TABLE IF NOT EXISTS questionnaire_external_push_logs (
    id BIGSERIAL PRIMARY KEY,
    questionnaire_id BIGINT NOT NULL REFERENCES questionnaires(id) ON DELETE CASCADE,
    questionnaire_title_snapshot TEXT NOT NULL DEFAULT '',
    submission_record_id BIGINT NOT NULL REFERENCES questionnaire_submissions(id) ON DELETE CASCADE,
    retry_from_log_id BIGINT REFERENCES questionnaire_external_push_logs(id) ON DELETE SET NULL,
    retry_attempt INTEGER NOT NULL DEFAULT 0,
    user_id TEXT NOT NULL DEFAULT '',
    target_url TEXT NOT NULL DEFAULT '',
    request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_status_code INTEGER,
    response_body TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'failed',
    failure_reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_questionnaire
ON questionnaire_external_push_logs (questionnaire_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_status
ON questionnaire_external_push_logs (status, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_submission
ON questionnaire_external_push_logs (submission_record_id);

CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_retry_from
ON questionnaire_external_push_logs (retry_from_log_id, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_channel (
    id BIGSERIAL PRIMARY KEY,
    channel_code TEXT NOT NULL UNIQUE,
    channel_name TEXT NOT NULL DEFAULT '',
    qr_url TEXT NOT NULL DEFAULT '',
    qr_ticket TEXT NOT NULL DEFAULT '',
    scene_value TEXT NOT NULL DEFAULT '',
    welcome_message TEXT NOT NULL DEFAULT '',
    auto_accept_friend BOOLEAN NOT NULL DEFAULT FALSE,
    owner_staff_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'inactive',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_channel_status
ON automation_channel (status, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_channel_scene
ON automation_channel (scene_value);

CREATE TABLE IF NOT EXISTS automation_member (
    id BIGSERIAL PRIMARY KEY,
    external_contact_id TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    master_customer_id BIGINT REFERENCES people(id) ON DELETE SET NULL,
    owner_staff_id TEXT NOT NULL DEFAULT '',
    in_pool BOOLEAN NOT NULL DEFAULT FALSE,
    current_pool TEXT NOT NULL DEFAULT 'removed',
    follow_type TEXT NOT NULL DEFAULT '',
    activation_status TEXT NOT NULL DEFAULT 'unknown',
    questionnaire_status TEXT NOT NULL DEFAULT 'pending',
    questionnaire_result TEXT NOT NULL DEFAULT 'unknown',
    decision_source TEXT NOT NULL DEFAULT 'system',
    source_type TEXT NOT NULL DEFAULT 'system',
    source_channel_id BIGINT REFERENCES automation_channel(id) ON DELETE SET NULL,
    last_active_pool TEXT NOT NULL DEFAULT '',
    joined_at TEXT NOT NULL DEFAULT '',
    last_ai_push_at TEXT NOT NULL DEFAULT '',
    ai_cooldown_until TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_member_external_non_empty
ON automation_member (external_contact_id)
WHERE external_contact_id <> '';

CREATE INDEX IF NOT EXISTS idx_automation_member_phone
ON automation_member (phone);

CREATE INDEX IF NOT EXISTS idx_automation_member_pool
ON automation_member (current_pool, in_pool);

CREATE INDEX IF NOT EXISTS idx_automation_member_owner
ON automation_member (owner_staff_id);

CREATE INDEX IF NOT EXISTS idx_automation_member_channel
ON automation_member (source_channel_id);

CREATE TABLE IF NOT EXISTS automation_event (
    id BIGSERIAL PRIMARY KEY,
    member_id BIGINT NOT NULL REFERENCES automation_member(id) ON DELETE CASCADE,
    action TEXT NOT NULL DEFAULT '',
    operator_type TEXT NOT NULL DEFAULT 'system',
    operator_id TEXT NOT NULL DEFAULT '',
    before_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    after_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    remark TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_event_member_created
ON automation_event (member_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_event_action_created
ON automation_event (action, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_ai_push_log (
    id BIGSERIAL PRIMARY KEY,
    member_id BIGINT NOT NULL REFERENCES automation_member(id) ON DELETE CASCADE,
    scene TEXT NOT NULL DEFAULT 'sidebar_script',
    request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'accepted',
    request_id TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    pushed_at TEXT NOT NULL DEFAULT '',
    cooldown_until TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_automation_ai_push_log_member_pushed
ON automation_ai_push_log (member_id, pushed_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_ai_push_log_status
ON automation_ai_push_log (status, pushed_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_message_activity_sync_run (
    id BIGSERIAL PRIMARY KEY,
    trigger_source TEXT NOT NULL DEFAULT 'manual',
    operator_type TEXT NOT NULL DEFAULT 'system',
    operator_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'success',
    candidate_count INTEGER NOT NULL DEFAULT 0,
    matched_count INTEGER NOT NULL DEFAULT 0,
    updated_count INTEGER NOT NULL DEFAULT 0,
    skipped_ambiguous_count INTEGER NOT NULL DEFAULT 0,
    skipped_unmatched_count INTEGER NOT NULL DEFAULT 0,
    skipped_missing_phone_count INTEGER NOT NULL DEFAULT 0,
    focus_count INTEGER NOT NULL DEFAULT 0,
    normal_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NOT NULL DEFAULT '',
    summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_run_finished
ON automation_message_activity_sync_run (finished_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_run_status
ON automation_message_activity_sync_run (status, finished_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_message_activity_sync_item (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES automation_message_activity_sync_run(id) ON DELETE CASCADE,
    member_id BIGINT REFERENCES automation_member(id) ON DELETE CASCADE,
    external_contact_id TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    phone_last4 TEXT NOT NULL DEFAULT '',
    message_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'updated',
    detail TEXT NOT NULL DEFAULT '',
    before_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    after_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_run
ON automation_message_activity_sync_item (run_id, id ASC);

CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_status
ON automation_message_activity_sync_item (status, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_last4
ON automation_message_activity_sync_item (phone_last4, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_focus_send_batch (
    id BIGSERIAL PRIMARY KEY,
    stage_key TEXT NOT NULL DEFAULT '',
    pool_key TEXT NOT NULL DEFAULT '',
    operator_type TEXT NOT NULL DEFAULT 'user',
    operator_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    total_count INTEGER NOT NULL DEFAULT 0,
    sent_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    cancelled_count INTEGER NOT NULL DEFAULT 0,
    next_run_at TEXT NOT NULL DEFAULT '',
    last_run_at TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_automation_focus_send_batch_stage_status
ON automation_focus_send_batch (stage_key, status, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_focus_send_batch_due
ON automation_focus_send_batch (status, next_run_at, id ASC);

CREATE TABLE IF NOT EXISTS automation_focus_send_batch_item (
    id BIGSERIAL PRIMARY KEY,
    batch_id BIGINT NOT NULL REFERENCES automation_focus_send_batch(id) ON DELETE CASCADE,
    member_id BIGINT REFERENCES automation_member(id) ON DELETE SET NULL,
    external_contact_id TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    position_index INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    detail TEXT NOT NULL DEFAULT '',
    result_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT NOT NULL DEFAULT '',
    finished_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_automation_focus_send_batch_item_batch_position
ON automation_focus_send_batch_item (batch_id, position_index ASC, id ASC);

CREATE INDEX IF NOT EXISTS idx_automation_focus_send_batch_item_status
ON automation_focus_send_batch_item (status, updated_at DESC, id DESC);
