CREATE TABLE IF NOT EXISTS archived_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seq INTEGER,
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
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_archived_messages_external_send_time
ON archived_messages (external_userid, send_time);

CREATE INDEX IF NOT EXISTS idx_archived_messages_owner_send_time
ON archived_messages (owner_userid, send_time);

CREATE INDEX IF NOT EXISTS idx_archived_messages_seq
ON archived_messages (seq);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_userid TEXT NOT NULL UNIQUE,
    customer_name TEXT,
    owner_userid TEXT,
    remark TEXT,
    description TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_contacts_owner_userid
ON contacts (owner_userid);

CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mobile TEXT NOT NULL UNIQUE,
    third_party_user_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS external_contact_bindings (
    external_userid TEXT PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE RESTRICT,
    first_bound_by_userid TEXT NOT NULL DEFAULT '',
    first_owner_userid TEXT NOT NULL DEFAULT '',
    last_owner_userid TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_external_contact_bindings_person_id
ON external_contact_bindings (person_id);

CREATE TABLE IF NOT EXISTS group_chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL UNIQUE,
    group_name TEXT,
    owner_userid TEXT,
    notice TEXT,
    member_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    create_time TEXT,
    dismissed_at TEXT,
    raw_payload TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_group_chats_owner_userid
ON group_chats (owner_userid);

CREATE INDEX IF NOT EXISTS idx_group_chats_status
ON group_chats (status);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    owner_userid TEXT,
    cursor TEXT,
    fetched_count INTEGER NOT NULL DEFAULT 0,
    inserted_count INTEGER NOT NULL DEFAULT 0,
    raw_response TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sync_runs_status_finished_at
ON sync_runs (status, finished_at);

CREATE TABLE IF NOT EXISTS outbound_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    request_payload TEXT NOT NULL,
    response_payload TEXT NOT NULL,
    wecom_task_id TEXT,
    status TEXT NOT NULL DEFAULT 'created',
    trace_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_outbound_tasks_trace
ON outbound_tasks (trace_id, id DESC);

CREATE TABLE IF NOT EXISTS outbound_webhook_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    source_key TEXT NOT NULL DEFAULT '',
    source_id TEXT NOT NULL DEFAULT '',
    target_url TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    payload_summary TEXT NOT NULL DEFAULT '',
    token_configured INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    response_status_code INTEGER,
    response_body_summary TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    last_attempted_at TEXT NOT NULL DEFAULT '',
    next_retry_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_outbound_webhook_deliveries_event_created
ON outbound_webhook_deliveries (event_type, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_outbound_webhook_deliveries_status_created
ON outbound_webhook_deliveries (status, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_outbound_webhook_deliveries_next_retry
ON outbound_webhook_deliveries (next_retry_at, status);

CREATE TABLE IF NOT EXISTS contact_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_userid TEXT NOT NULL,
    userid TEXT NOT NULL,
    tag_id TEXT NOT NULL,
    tag_name TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (external_userid, userid, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_contact_tags_external_userid
ON contact_tags (external_userid);

CREATE TABLE IF NOT EXISTS owner_role_map (
    userid TEXT PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_owner_role_map_active
ON owner_role_map (active);

CREATE TABLE IF NOT EXISTS signup_tag_rules (
    tag_id TEXT PRIMARY KEY,
    tag_name TEXT NOT NULL DEFAULT '',
    signup_status TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    set_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    wecom_tag_sync_status TEXT NOT NULL DEFAULT 'pending',
    wecom_tag_sync_error TEXT NOT NULL DEFAULT '',
    status_flags_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_class_user_status_current_signup_status
ON class_user_status_current (signup_status);

CREATE INDEX IF NOT EXISTS idx_class_user_status_current_set_at
ON class_user_status_current (set_at);

CREATE TABLE IF NOT EXISTS class_user_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_userid TEXT NOT NULL,
    old_signup_status TEXT NOT NULL DEFAULT '',
    new_signup_status TEXT NOT NULL DEFAULT '',
    old_label_name TEXT NOT NULL DEFAULT '',
    new_label_name TEXT NOT NULL DEFAULT '',
    customer_name_snapshot TEXT NOT NULL DEFAULT '',
    owner_userid_snapshot TEXT NOT NULL DEFAULT '',
    mobile_snapshot TEXT NOT NULL DEFAULT '',
    set_by_userid TEXT NOT NULL DEFAULT '',
    set_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    wecom_tag_sync_status TEXT NOT NULL DEFAULT 'pending',
    wecom_tag_sync_error TEXT NOT NULL DEFAULT '',
    status_flags_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_class_user_status_history_external_userid
ON class_user_status_history (external_userid, created_at DESC);

CREATE TABLE IF NOT EXISTS user_ops_pool_current (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mobile TEXT NOT NULL DEFAULT '',
    external_userid TEXT NOT NULL DEFAULT '',
    customer_name TEXT NOT NULL DEFAULT '',
    owner_userid TEXT NOT NULL DEFAULT '',
    current_status TEXT NOT NULL DEFAULT 'lead_trial',
    is_wecom_bound INTEGER NOT NULL DEFAULT 0,
    activation_status TEXT NOT NULL DEFAULT 'not_activated',
    activation_remark TEXT NOT NULL DEFAULT '',
    class_term_no INTEGER,
    class_term_label TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_userid TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'manual',
    reason_code TEXT NOT NULL DEFAULT '',
    reason_text TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL DEFAULT 'private_message',
    outbound_task_ids_json TEXT NOT NULL DEFAULT '[]',
    task_results_json TEXT NOT NULL DEFAULT '[]',
    selected_count INTEGER NOT NULL DEFAULT 0,
    eligible_count INTEGER NOT NULL DEFAULT 0,
    sent_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    skipped_reasons_json TEXT NOT NULL DEFAULT '{}',
    include_do_not_disturb INTEGER NOT NULL DEFAULT 0,
    content_preview TEXT NOT NULL DEFAULT '',
    image_count INTEGER NOT NULL DEFAULT 0,
    sender_userids_json TEXT NOT NULL DEFAULT '[]',
    filter_snapshot_json TEXT NOT NULL DEFAULT '{}',
    operator TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'created',
    last_status_sync_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_ops_send_records_created
ON user_ops_send_records (created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS user_ops_experience_leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mobile TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL DEFAULT 'experience_import',
    import_batch_id INTEGER,
    created_by TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_ops_experience_leads_active
ON user_ops_experience_leads (is_active);

CREATE TABLE IF NOT EXISTS user_ops_import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_type TEXT NOT NULL DEFAULT '',
    file_name TEXT NOT NULL DEFAULT '',
    total_rows INTEGER NOT NULL DEFAULT 0,
    success_rows INTEGER NOT NULL DEFAULT 0,
    failed_rows INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_ops_import_batches_type_created
ON user_ops_import_batches (import_type, created_at DESC);

CREATE TABLE IF NOT EXISTS user_ops_activation_status_source (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mobile TEXT NOT NULL UNIQUE,
    activation_status TEXT NOT NULL DEFAULT 'not_activated'
        CHECK (activation_status IN ('not_activated', 'activated', 'high_intent')),
    activation_remark TEXT NOT NULL DEFAULT '',
    import_batch_id INTEGER,
    created_by TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_ops_activation_status_source_active
ON user_ops_activation_status_source (is_active);

CREATE TABLE IF NOT EXISTS user_ops_lead_pool_current (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mobile TEXT NOT NULL DEFAULT '',
    external_userid TEXT NOT NULL DEFAULT '',
    customer_name TEXT NOT NULL DEFAULT '',
    owner_userid TEXT NOT NULL DEFAULT '',
    is_wecom_added INTEGER NOT NULL DEFAULT 0,
    is_mobile_bound INTEGER NOT NULL DEFAULT 0,
    huangxiaocan_activation_state TEXT NOT NULL DEFAULT 'unknown'
        CHECK (huangxiaocan_activation_state IN ('unknown', 'activated', 'not_activated')),
    class_term_no INTEGER,
    class_term_label TEXT NOT NULL DEFAULT '',
    first_entry_source TEXT NOT NULL DEFAULT '',
    last_entry_source TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mobile TEXT NOT NULL DEFAULT '',
    external_userid TEXT NOT NULL DEFAULT '',
    action_type TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT '',
    operator TEXT NOT NULL DEFAULT '',
    before_json TEXT NOT NULL DEFAULT '{}',
    after_json TEXT NOT NULL DEFAULT '{}',
    remark TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_ops_lead_pool_history_mobile
ON user_ops_lead_pool_history (mobile);

CREATE INDEX IF NOT EXISTS idx_user_ops_lead_pool_history_external
ON user_ops_lead_pool_history (external_userid);

CREATE INDEX IF NOT EXISTS idx_user_ops_lead_pool_history_created
ON user_ops_lead_pool_history (created_at DESC);

CREATE TABLE IF NOT EXISTS user_ops_huangxiaocan_activation_source (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mobile TEXT NOT NULL UNIQUE,
    activation_state TEXT NOT NULL
        CHECK (activation_state IN ('activated', 'not_activated')),
    import_batch_id TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_ops_huangxiaocan_activation_source_active
ON user_ops_huangxiaocan_activation_source (is_active);

CREATE TABLE IF NOT EXISTS user_ops_deferred_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL DEFAULT '',
    tenant_key TEXT NOT NULL DEFAULT 'aicrm',
    external_userid TEXT NOT NULL DEFAULT '',
    owner_userid TEXT NOT NULL DEFAULT '',
    run_after TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'success', 'skipped', 'conflict', 'failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_ops_deferred_jobs_status_run_after
ON user_ops_deferred_jobs (status, run_after);

CREATE INDEX IF NOT EXISTS idx_user_ops_deferred_jobs_owner_external
ON user_ops_deferred_jobs (owner_userid, external_userid);

CREATE INDEX IF NOT EXISTS idx_user_ops_deferred_jobs_job_tenant_status
ON user_ops_deferred_jobs (job_type, tenant_key, status, run_after, id DESC);

CREATE TABLE IF NOT EXISTS user_ops_pool_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_id INTEGER,
    mobile TEXT NOT NULL DEFAULT '',
    external_userid TEXT NOT NULL DEFAULT '',
    action_type TEXT NOT NULL DEFAULT '',
    old_payload_json TEXT NOT NULL DEFAULT '{}',
    new_payload_json TEXT NOT NULL DEFAULT '{}',
    operator TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL DEFAULT '',
    group_id TEXT NOT NULL DEFAULT '',
    tag_id TEXT NOT NULL DEFAULT '',
    tag_group_name TEXT NOT NULL DEFAULT '',
    tag_name TEXT NOT NULL DEFAULT '',
    class_term_no INTEGER NOT NULL,
    class_term_label TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_class_term_tag_mapping_group_tag
ON class_term_tag_mapping (tag_group_name, tag_name);

CREATE UNIQUE INDEX IF NOT EXISTS uq_class_term_tag_mapping_tag_id_non_empty
ON class_term_tag_mapping (tag_id)
WHERE tag_id <> '';

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    active INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_routing_rule_config_active
ON routing_rule_config (active);

CREATE TABLE IF NOT EXISTS mcp_tool_settings (
    tool_name TEXT PRIMARY KEY,
    tool_group TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    description_override TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    visible_in_console INTEGER NOT NULL DEFAULT 1,
    show_sample_args INTEGER NOT NULL DEFAULT 0,
    show_sample_output INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mcp_tool_settings_enabled
ON mcp_tool_settings (enabled);

CREATE TABLE IF NOT EXISTS admin_operation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operator TEXT NOT NULL DEFAULT '',
    action_type TEXT NOT NULL DEFAULT '',
    target_type TEXT NOT NULL DEFAULT '',
    target_id TEXT NOT NULL DEFAULT '',
    before_json TEXT NOT NULL DEFAULT '{}',
    after_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_admin_operation_logs_target
ON admin_operation_logs (target_type, target_id, created_at DESC);

CREATE TABLE IF NOT EXISTS admin_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wecom_userid TEXT NOT NULL,
    wecom_corpid TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    auth_source TEXT NOT NULL DEFAULT 'wecom_sso',
    last_login_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_admin_users_wecom_identity
ON admin_users (wecom_corpid, wecom_userid);

CREATE INDEX IF NOT EXISTS idx_admin_users_active_identity
ON admin_users (is_active, display_name, wecom_userid);

CREATE TABLE IF NOT EXISTS admin_user_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_user_id INTEGER NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    role_code TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_admin_user_roles_binding
ON admin_user_roles (admin_user_id, role_code);

CREATE INDEX IF NOT EXISTS idx_admin_user_roles_role_code
ON admin_user_roles (role_code, admin_user_id);

CREATE TABLE IF NOT EXISTS admin_login_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_user_id INTEGER REFERENCES admin_users(id) ON DELETE SET NULL,
    login_type TEXT NOT NULL DEFAULT '',
    login_result TEXT NOT NULL DEFAULT '',
    ip TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_admin_login_audit_created
ON admin_login_audit (created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS admin_sso_states (
    state_token TEXT PRIMARY KEY,
    login_kind TEXT NOT NULL DEFAULT 'wecom_qr',
    next_path TEXT NOT NULL DEFAULT '/admin/automation-conversion',
    expires_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_admin_sso_states_expires
ON admin_sso_states (expires_at);

CREATE TABLE IF NOT EXISTS archive_sync_state (
    state_key TEXT PRIMARY KEY,
    last_seq INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS message_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_key TEXT NOT NULL UNIQUE,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    message_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    acked_at TEXT,
    ack_note TEXT,
    acked_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_message_batches_status_window
ON message_batches (status, window_start);

CREATE TABLE IF NOT EXISTS message_batch_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES message_batches(id) ON DELETE CASCADE,
    message_id INTEGER NOT NULL REFERENCES archived_messages(id) ON DELETE CASCADE,
    msgid TEXT NOT NULL,
    chat_type TEXT NOT NULL,
    chat_id TEXT,
    external_userid TEXT,
    owner_userid TEXT,
    send_time TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (message_id)
);

CREATE INDEX IF NOT EXISTS idx_message_batch_items_batch_id
ON message_batch_items (batch_id);

CREATE INDEX IF NOT EXISTS idx_message_batch_items_external_userid
ON message_batch_items (external_userid);

CREATE TABLE IF NOT EXISTS conversion_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_userid TEXT,
    chat_id TEXT,
    feedback_type TEXT NOT NULL,
    feedback_payload TEXT NOT NULL DEFAULT '{}',
    actor TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS marketing_state_current (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_key TEXT NOT NULL DEFAULT 'signup_conversion_v1',
    external_userid TEXT NOT NULL,
    marketing_phase TEXT NOT NULL DEFAULT 'awaiting_trigger',
    phase_label TEXT NOT NULL DEFAULT '',
    phase_reason TEXT NOT NULL DEFAULT '',
    lifecycle_status TEXT NOT NULL DEFAULT 'idle',
    last_batch_id INTEGER,
    last_batch_status TEXT NOT NULL DEFAULT '',
    last_batch_window_start TEXT NOT NULL DEFAULT '',
    last_batch_window_end TEXT NOT NULL DEFAULT '',
    last_trigger_message_at TEXT NOT NULL DEFAULT '',
    entered_at TEXT,
    exited_at TEXT,
    exit_reason TEXT NOT NULL DEFAULT '',
    source_payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (scenario_key, external_userid)
);

CREATE INDEX IF NOT EXISTS idx_marketing_state_current_phase
ON marketing_state_current (scenario_key, marketing_phase, lifecycle_status);

CREATE INDEX IF NOT EXISTS idx_marketing_state_current_external
ON marketing_state_current (external_userid, scenario_key);

CREATE TABLE IF NOT EXISTS marketing_value_segment_current (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_key TEXT NOT NULL DEFAULT 'signup_conversion_v1',
    external_userid TEXT NOT NULL,
    value_segment TEXT NOT NULL DEFAULT 'normal',
    segment_label TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    score_breakdown_json TEXT NOT NULL DEFAULT '{}',
    source_payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (scenario_key, external_userid)
);

CREATE INDEX IF NOT EXISTS idx_marketing_value_segment_current_segment
ON marketing_value_segment_current (scenario_key, value_segment, score DESC);

CREATE INDEX IF NOT EXISTS idx_marketing_value_segment_current_external
ON marketing_value_segment_current (external_userid, scenario_key);

CREATE TABLE IF NOT EXISTS marketing_automation_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    automation_key TEXT NOT NULL UNIQUE,
    automation_name TEXT NOT NULL DEFAULT '',
    target_event TEXT NOT NULL DEFAULT 'signup_success',
    channel_type TEXT NOT NULL DEFAULT 'text_message',
    status TEXT NOT NULL DEFAULT 'active',
    do_not_start_after_hour INTEGER NOT NULL DEFAULT 23,
    config_payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_marketing_automation_configs_status
ON marketing_automation_configs (status);

CREATE TABLE IF NOT EXISTS marketing_automation_question_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    automation_config_id INTEGER NOT NULL REFERENCES marketing_automation_configs(id) ON DELETE CASCADE,
    questionnaire_id INTEGER,
    question_id INTEGER,
    rule_code TEXT NOT NULL DEFAULT '',
    rule_name TEXT NOT NULL DEFAULT '',
    answer_match_type TEXT NOT NULL DEFAULT 'any_of',
    answer_match_value_json TEXT NOT NULL DEFAULT '[]',
    score_delta INTEGER NOT NULL DEFAULT 0,
    segment_hint TEXT NOT NULL DEFAULT '',
    stage_hint TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    rule_payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (automation_config_id, question_id, rule_code)
);

CREATE INDEX IF NOT EXISTS idx_marketing_automation_question_rules_config
ON marketing_automation_question_rules (automation_config_id, is_active, sort_order, id);

CREATE INDEX IF NOT EXISTS idx_marketing_automation_question_rules_question
ON marketing_automation_question_rules (question_id);

CREATE TABLE IF NOT EXISTS customer_value_segment_current (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_userid TEXT NOT NULL UNIQUE,
    segment TEXT NOT NULL DEFAULT 'normal',
    segment_rank INTEGER NOT NULL DEFAULT 0,
    score INTEGER NOT NULL DEFAULT 0,
    scoring_version TEXT NOT NULL DEFAULT '',
    computed_reason TEXT NOT NULL DEFAULT '',
    submission_id INTEGER REFERENCES questionnaire_submissions(id) ON DELETE SET NULL,
    matched_question_ids_json TEXT NOT NULL DEFAULT '[]',
    source_payload_json TEXT NOT NULL DEFAULT '{}',
    evaluated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    computed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_customer_value_segment_current_external_userid
ON customer_value_segment_current (external_userid);

CREATE INDEX IF NOT EXISTS idx_customer_value_segment_current_segment
ON customer_value_segment_current (segment);

CREATE TABLE IF NOT EXISTS customer_value_segment_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_userid TEXT NOT NULL,
    segment TEXT NOT NULL DEFAULT 'normal',
    segment_rank INTEGER NOT NULL DEFAULT 0,
    score INTEGER NOT NULL DEFAULT 0,
    scoring_version TEXT NOT NULL DEFAULT '',
    change_reason TEXT NOT NULL DEFAULT '',
    submission_id INTEGER REFERENCES questionnaire_submissions(id) ON DELETE SET NULL,
    matched_question_ids_json TEXT NOT NULL DEFAULT '[]',
    source_payload_json TEXT NOT NULL DEFAULT '{}',
    evaluated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_customer_value_segment_history_external_userid
ON customer_value_segment_history (external_userid, recorded_at DESC);

CREATE TABLE IF NOT EXISTS customer_marketing_state_current (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
    external_userid TEXT NOT NULL DEFAULT '',
    automation_key TEXT NOT NULL DEFAULT 'signup_conversion_v1',
    main_stage TEXT NOT NULL DEFAULT 'pending',
    sub_stage TEXT NOT NULL DEFAULT '',
    activated INTEGER NOT NULL DEFAULT 0,
    converted INTEGER NOT NULL DEFAULT 0,
    eligible_for_conversion INTEGER NOT NULL DEFAULT 0,
    lifecycle_status TEXT NOT NULL DEFAULT 'idle',
    last_activation_at TEXT NOT NULL DEFAULT '',
    last_conversion_marked_at TEXT NOT NULL DEFAULT '',
    last_message_at TEXT NOT NULL DEFAULT '',
    last_batch_id INTEGER REFERENCES message_batches(id) ON DELETE SET NULL,
    last_batch_status TEXT NOT NULL DEFAULT '',
    last_batch_window_start TEXT NOT NULL DEFAULT '',
    last_batch_window_end TEXT NOT NULL DEFAULT '',
    last_trigger_message_at TEXT NOT NULL DEFAULT '',
    entered_at TEXT,
    exited_at TEXT,
    exit_reason TEXT NOT NULL DEFAULT '',
    state_payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
    external_userid TEXT NOT NULL DEFAULT '',
    automation_key TEXT NOT NULL DEFAULT 'signup_conversion_v1',
    main_stage TEXT NOT NULL DEFAULT 'pending',
    sub_stage TEXT NOT NULL DEFAULT '',
    activated INTEGER NOT NULL DEFAULT 0,
    converted INTEGER NOT NULL DEFAULT 0,
    eligible_for_conversion INTEGER NOT NULL DEFAULT 0,
    batch_id INTEGER REFERENCES message_batches(id) ON DELETE SET NULL,
    lifecycle_status TEXT NOT NULL DEFAULT 'idle',
    exit_reason TEXT NOT NULL DEFAULT '',
    last_activation_at TEXT NOT NULL DEFAULT '',
    last_conversion_marked_at TEXT NOT NULL DEFAULT '',
    last_message_at TEXT NOT NULL DEFAULT '',
    change_reason TEXT NOT NULL DEFAULT '',
    state_payload_json TEXT NOT NULL DEFAULT '{}',
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_history_external_userid
ON customer_marketing_state_history (external_userid, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_history_person_id
ON customer_marketing_state_history (person_id, recorded_at DESC);


CREATE TABLE IF NOT EXISTS conversion_dispatch_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    automation_key TEXT NOT NULL DEFAULT 'signup_conversion_v1',
    batch_id INTEGER NOT NULL REFERENCES message_batches(id) ON DELETE CASCADE,
    external_userid TEXT NOT NULL,
    dispatch_status TEXT NOT NULL DEFAULT 'pending',
    dispatch_channel TEXT NOT NULL DEFAULT 'text_message',
    dispatch_payload_json TEXT NOT NULL DEFAULT '{}',
    dispatch_note TEXT NOT NULL DEFAULT '',
    dispatched_at TEXT,
    acked_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (batch_id, external_userid)
);

CREATE INDEX IF NOT EXISTS idx_conversion_dispatch_log_batch_id
ON conversion_dispatch_log (batch_id);

CREATE INDEX IF NOT EXISTS idx_conversion_dispatch_log_external_userid
ON conversion_dispatch_log (external_userid);

CREATE INDEX IF NOT EXISTS idx_conversion_dispatch_log_dispatch_status
ON conversion_dispatch_log (dispatch_status);

CREATE TABLE IF NOT EXISTS wecom_external_contact_identity_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    corp_id TEXT NOT NULL,
    external_userid TEXT NOT NULL,
    unionid TEXT NOT NULL DEFAULT '',
    openid TEXT NOT NULL DEFAULT '',
    follow_user_userid TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    type INTEGER,
    avatar TEXT NOT NULL DEFAULT '',
    gender INTEGER,
    status TEXT NOT NULL DEFAULT 'active',
    raw_profile TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    corp_id TEXT NOT NULL,
    external_userid TEXT NOT NULL,
    user_id TEXT NOT NULL,
    relation_status TEXT NOT NULL DEFAULT 'active',
    is_primary INTEGER NOT NULL DEFAULT 0,
    remark TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    add_way INTEGER,
    state TEXT NOT NULL DEFAULT '',
    oper_userid TEXT NOT NULL DEFAULT '',
    createtime INTEGER,
    raw_follow_user TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (corp_id, external_userid, user_id)
);

CREATE INDEX IF NOT EXISTS idx_external_contact_follow_users_external
ON wecom_external_contact_follow_users (corp_id, external_userid);

CREATE INDEX IF NOT EXISTS idx_external_contact_follow_users_user
ON wecom_external_contact_follow_users (user_id);

CREATE INDEX IF NOT EXISTS idx_external_contact_follow_users_status
ON wecom_external_contact_follow_users (relation_status);

CREATE TABLE IF NOT EXISTS wecom_external_contact_event_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    corp_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    change_type TEXT NOT NULL,
    external_userid TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    event_time INTEGER,
    event_key TEXT NOT NULL UNIQUE,
    payload_xml TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    process_status TEXT NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_external_contact_event_logs_status
ON wecom_external_contact_event_logs (process_status, updated_at);

CREATE TABLE IF NOT EXISTS questionnaires (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_disabled INTEGER NOT NULL DEFAULT 0,
    redirect_url TEXT NOT NULL DEFAULT '',
    external_push_enabled INTEGER NOT NULL DEFAULT 0,
    external_push_url TEXT NOT NULL DEFAULT '',
    external_push_day INTEGER,
    external_push_frequency INTEGER,
    external_push_remark TEXT NOT NULL DEFAULT '',
    external_push_custom_params TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_questionnaires_slug
ON questionnaires (slug);

CREATE INDEX IF NOT EXISTS idx_questionnaires_external_push_enabled
ON questionnaires (external_push_enabled);

CREATE INDEX IF NOT EXISTS idx_questionnaires_disabled
ON questionnaires (is_disabled);

CREATE TABLE IF NOT EXISTS questionnaire_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    questionnaire_id INTEGER NOT NULL REFERENCES questionnaires(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('single_choice', 'multi_choice', 'textarea', 'mobile')),
    title TEXT NOT NULL,
    placeholder_text TEXT NOT NULL DEFAULT '',
    required INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_questionnaire_questions_questionnaire
ON questionnaire_questions (questionnaire_id, sort_order, id);

CREATE TABLE IF NOT EXISTS questionnaire_options (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL REFERENCES questionnaire_questions(id) ON DELETE CASCADE,
    option_text TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 0,
    tag_codes TEXT NOT NULL DEFAULT '[]',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_questionnaire_options_question
ON questionnaire_options (question_id, sort_order, id);

CREATE TABLE IF NOT EXISTS questionnaire_score_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    questionnaire_id INTEGER NOT NULL REFERENCES questionnaires(id) ON DELETE CASCADE,
    min_score REAL,
    max_score REAL,
    tag_codes TEXT NOT NULL DEFAULT '[]',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_questionnaire_score_rules_questionnaire
ON questionnaire_score_rules (questionnaire_id, sort_order, id);

CREATE TABLE IF NOT EXISTS questionnaire_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    questionnaire_id INTEGER NOT NULL REFERENCES questionnaires(id) ON DELETE CASCADE,
    identity_map_id INTEGER REFERENCES wecom_external_contact_identity_map(id) ON DELETE SET NULL,
    respondent_key TEXT NOT NULL DEFAULT '',
    openid TEXT NOT NULL DEFAULT '',
    unionid TEXT NOT NULL DEFAULT '',
    external_userid TEXT NOT NULL DEFAULT '',
    follow_user_userid TEXT NOT NULL DEFAULT '',
    matched_by TEXT NOT NULL DEFAULT '',
    mobile_snapshot TEXT NOT NULL DEFAULT '',
    source_channel TEXT NOT NULL DEFAULT '',
    campaign_id TEXT NOT NULL DEFAULT '',
    staff_id TEXT NOT NULL DEFAULT '',
    total_score REAL NOT NULL DEFAULT 0,
    final_tags TEXT NOT NULL DEFAULT '[]',
    redirect_url_snapshot TEXT NOT NULL DEFAULT '',
    submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_questionnaire_submissions_questionnaire
ON questionnaire_submissions (questionnaire_id, submitted_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_questionnaire_submissions_identity_map
ON questionnaire_submissions (identity_map_id);

CREATE INDEX IF NOT EXISTS idx_questionnaire_submissions_external
ON questionnaire_submissions (external_userid);

CREATE TABLE IF NOT EXISTS questionnaire_submission_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL REFERENCES questionnaire_submissions(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL,
    question_type TEXT NOT NULL,
    question_title_snapshot TEXT NOT NULL,
    selected_option_ids TEXT NOT NULL DEFAULT '[]',
    selected_option_texts_snapshot TEXT NOT NULL DEFAULT '[]',
    selected_option_scores_snapshot TEXT NOT NULL DEFAULT '[]',
    selected_option_tags_snapshot TEXT NOT NULL DEFAULT '[]',
    text_value TEXT NOT NULL DEFAULT '',
    score_contribution REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_questionnaire_submission_answers_submission
ON questionnaire_submission_answers (submission_id, id);

CREATE INDEX IF NOT EXISTS idx_questionnaire_submission_answers_question
ON questionnaire_submission_answers (question_id);

CREATE TABLE IF NOT EXISTS questionnaire_scrm_apply_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL REFERENCES questionnaire_submissions(id) ON DELETE CASCADE,
    external_userid TEXT NOT NULL DEFAULT '',
    follow_user_userid TEXT NOT NULL DEFAULT '',
    final_tags TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'skipped',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_questionnaire_scrm_apply_logs_submission
ON questionnaire_scrm_apply_logs (submission_id, id);

CREATE INDEX IF NOT EXISTS idx_questionnaire_scrm_apply_logs_status
ON questionnaire_scrm_apply_logs (status, created_at);

CREATE TABLE IF NOT EXISTS questionnaire_external_push_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    questionnaire_id INTEGER NOT NULL REFERENCES questionnaires(id) ON DELETE CASCADE,
    questionnaire_title_snapshot TEXT NOT NULL DEFAULT '',
    submission_record_id INTEGER NOT NULL REFERENCES questionnaire_submissions(id) ON DELETE CASCADE,
    retry_from_log_id INTEGER REFERENCES questionnaire_external_push_logs(id) ON DELETE SET NULL,
    retry_attempt INTEGER NOT NULL DEFAULT 0,
    user_id TEXT NOT NULL DEFAULT '',
    target_url TEXT NOT NULL DEFAULT '',
    request_payload TEXT NOT NULL DEFAULT '{}',
    response_status_code INTEGER,
    response_body TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'failed',
    failure_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id INTEGER,
    channel_code TEXT NOT NULL UNIQUE,
    channel_name TEXT NOT NULL DEFAULT '',
    qr_url TEXT NOT NULL DEFAULT '',
    qr_ticket TEXT NOT NULL DEFAULT '',
    scene_value TEXT NOT NULL DEFAULT '',
    welcome_message TEXT NOT NULL DEFAULT '',
    auto_accept_friend INTEGER NOT NULL DEFAULT 0,
    entry_tag_id TEXT NOT NULL DEFAULT '',
    entry_tag_name TEXT NOT NULL DEFAULT '',
    entry_tag_group_name TEXT NOT NULL DEFAULT '',
    owner_staff_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'inactive',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_channel_status
ON automation_channel (status, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_channel_program
ON automation_channel (program_id, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_channel_scene
ON automation_channel (scene_value);

CREATE TABLE IF NOT EXISTS automation_member (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_contact_id TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    master_customer_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
    owner_staff_id TEXT NOT NULL DEFAULT '',
    in_pool INTEGER NOT NULL DEFAULT 0,
    current_pool TEXT NOT NULL DEFAULT 'removed',
    follow_type TEXT NOT NULL DEFAULT '',
    questionnaire_status TEXT NOT NULL DEFAULT 'pending',
    decision_source TEXT NOT NULL DEFAULT 'system',
    source_type TEXT NOT NULL DEFAULT 'system',
    source_channel_id INTEGER REFERENCES automation_channel(id) ON DELETE SET NULL,
    current_audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire'
        CHECK (current_audience_code IN ('pending_questionnaire', 'operating', 'converted')),
    current_audience_entered_at TEXT NOT NULL DEFAULT '',
    last_active_pool TEXT NOT NULL DEFAULT '',
    joined_at TEXT NOT NULL DEFAULT '',
    last_ai_push_at TEXT NOT NULL DEFAULT '',
    ai_cooldown_until TEXT NOT NULL DEFAULT '',
    profile_segment_key TEXT NOT NULL DEFAULT '',
    behavior_tier_key TEXT NOT NULL DEFAULT '',
    segment_refreshed_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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

CREATE INDEX IF NOT EXISTS idx_automation_member_audience
ON automation_member (current_audience_code, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_member_segments
ON automation_member (current_audience_code, profile_segment_key, behavior_tier_key);

CREATE TABLE IF NOT EXISTS automation_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL REFERENCES automation_member(id) ON DELETE CASCADE,
    action TEXT NOT NULL DEFAULT '',
    operator_type TEXT NOT NULL DEFAULT 'system',
    operator_id TEXT NOT NULL DEFAULT '',
    before_snapshot TEXT NOT NULL DEFAULT '{}',
    after_snapshot TEXT NOT NULL DEFAULT '{}',
    remark TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_event_member_created
ON automation_event (member_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_event_action_created
ON automation_event (action, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_ai_push_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL REFERENCES automation_member(id) ON DELETE CASCADE,
    scene TEXT NOT NULL DEFAULT 'sidebar_script',
    request_payload TEXT NOT NULL DEFAULT '{}',
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    summary_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_run_finished
ON automation_message_activity_sync_run (finished_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_run_status
ON automation_message_activity_sync_run (status, finished_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_message_activity_sync_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES automation_message_activity_sync_run(id) ON DELETE CASCADE,
    member_id INTEGER REFERENCES automation_member(id) ON DELETE CASCADE,
    external_contact_id TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    phone_prefix3 TEXT NOT NULL DEFAULT '',
    phone_last4 TEXT NOT NULL DEFAULT '',
    phone_match_key TEXT NOT NULL DEFAULT '',
    message_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'updated',
    detail TEXT NOT NULL DEFAULT '',
    before_snapshot TEXT NOT NULL DEFAULT '{}',
    after_snapshot TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_run
ON automation_message_activity_sync_item (run_id, id ASC);

CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_status
ON automation_message_activity_sync_item (status, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_last4
ON automation_message_activity_sync_item (phone_last4, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_match_key
ON automation_message_activity_sync_item (phone_match_key, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_reply_monitor_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_key TEXT NOT NULL UNIQUE DEFAULT 'default',
    enabled INTEGER NOT NULL DEFAULT 0,
    last_capture_cursor INTEGER NOT NULL DEFAULT 0,
    last_capture_at TEXT NOT NULL DEFAULT '',
    last_capture_status TEXT NOT NULL DEFAULT '',
    last_capture_summary_json TEXT NOT NULL DEFAULT '{}',
    last_dispatch_at TEXT NOT NULL DEFAULT '',
    last_dispatch_status TEXT NOT NULL DEFAULT '',
    last_dispatch_summary_json TEXT NOT NULL DEFAULT '{}',
    last_error TEXT NOT NULL DEFAULT '',
    quiet_hours_start TEXT NOT NULL DEFAULT '23:00',
    quiet_hours_end TEXT NOT NULL DEFAULT '09:00',
    dispatch_interval_seconds INTEGER NOT NULL DEFAULT 30,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_reply_monitor_config_updated
ON automation_reply_monitor_config (updated_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_reply_monitor_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER REFERENCES automation_member(id) ON DELETE SET NULL,
    external_userid TEXT NOT NULL DEFAULT '',
    owner_userid TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    message_ids_json TEXT NOT NULL DEFAULT '[]',
    message_count INTEGER NOT NULL DEFAULT 0,
    first_inbound_at TEXT NOT NULL DEFAULT '',
    last_inbound_at TEXT NOT NULL DEFAULT '',
    not_before TEXT NOT NULL DEFAULT '',
    last_dispatch_at TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    payload_snapshot_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_reply_monitor_queue_status_due
ON automation_reply_monitor_queue (status, not_before, id ASC);

CREATE INDEX IF NOT EXISTS idx_automation_reply_monitor_queue_external_updated
ON automation_reply_monitor_queue (external_userid, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_reply_monitor_queue_member_updated
ON automation_reply_monitor_queue (member_id, updated_at DESC, id DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_reply_monitor_queue_active_external
ON automation_reply_monitor_queue (external_userid)
WHERE external_userid <> ''
  AND status IN ('pending', 'deferred_quiet_hours', 'paused');

CREATE TABLE IF NOT EXISTS automation_laohuang_chat_job (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_id INTEGER REFERENCES automation_reply_monitor_queue(id) ON DELETE SET NULL,
    member_id INTEGER REFERENCES automation_member(id) ON DELETE SET NULL,
    external_contact_id TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    external_message_id TEXT NOT NULL DEFAULT '',
    external_session_id TEXT NOT NULL DEFAULT '',
    laohuang_task_id TEXT NOT NULL DEFAULT '',
    request_payload_json TEXT NOT NULL DEFAULT '{}',
    accepted_payload_json TEXT NOT NULL DEFAULT '{}',
    callback_payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'created',
    reply_text TEXT NOT NULL DEFAULT '',
    error_code TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    send_channel TEXT NOT NULL DEFAULT 'private_message',
    send_record_id INTEGER REFERENCES user_ops_send_records(id) ON DELETE SET NULL,
    send_result_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT NOT NULL DEFAULT ''
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_laohuang_chat_job_external_message
ON automation_laohuang_chat_job (external_message_id)
WHERE external_message_id <> '';

CREATE INDEX IF NOT EXISTS idx_automation_laohuang_chat_job_task
ON automation_laohuang_chat_job (laohuang_task_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_laohuang_chat_job_status_updated
ON automation_laohuang_chat_job (status, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_laohuang_chat_job_queue
ON automation_laohuang_chat_job (queue_id, id DESC);

CREATE TABLE IF NOT EXISTS automation_agent_prompt_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL DEFAULT '',
    prompt_text TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_agent_prompt_registry_enabled
ON automation_agent_prompt_registry (enabled, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_agent_prompt_registry_updated
ON automation_agent_prompt_registry (updated_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_agent_llm_call_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_code TEXT NOT NULL DEFAULT '',
    model_name TEXT NOT NULL DEFAULT '',
    request_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    latency_ms INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_agent_llm_call_log_agent_created
ON automation_agent_llm_call_log (agent_code, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_agent_llm_call_log_status_created
ON automation_agent_llm_call_log (status, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_agent_router_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_key TEXT NOT NULL UNIQUE DEFAULT 'default',
    enabled INTEGER NOT NULL DEFAULT 0,
    webhook_url TEXT NOT NULL DEFAULT '',
    signature_token TEXT NOT NULL DEFAULT '',
    signature_secret TEXT NOT NULL DEFAULT '',
    signature_header TEXT NOT NULL DEFAULT 'X-Lobster-Signature',
    timeout_seconds INTEGER NOT NULL DEFAULT 8,
    retry_count INTEGER NOT NULL DEFAULT 1,
    fallback_strategy_json TEXT NOT NULL DEFAULT '{}',
    request_sample_json TEXT NOT NULL DEFAULT '{}',
    response_sample_json TEXT NOT NULL DEFAULT '{}',
    last_status TEXT NOT NULL DEFAULT 'never_called',
    last_error TEXT NOT NULL DEFAULT '',
    last_called_at TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT '',
    updated_source TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_agent_router_config_updated
ON automation_agent_router_config (updated_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_agent_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL DEFAULT '',
    scenario_code TEXT NOT NULL DEFAULT 'one_to_one',
    pool_keys_json TEXT NOT NULL DEFAULT '[]',
    enabled INTEGER NOT NULL DEFAULT 1,
    draft_role_prompt TEXT NOT NULL DEFAULT '',
    draft_task_prompt TEXT NOT NULL DEFAULT '',
    draft_variables_json TEXT NOT NULL DEFAULT '[]',
    draft_output_schema_json TEXT NOT NULL DEFAULT '[]',
    published_role_prompt TEXT NOT NULL DEFAULT '',
    published_task_prompt TEXT NOT NULL DEFAULT '',
    published_variables_json TEXT NOT NULL DEFAULT '[]',
    published_output_schema_json TEXT NOT NULL DEFAULT '[]',
    draft_version INTEGER NOT NULL DEFAULT 1,
    published_version INTEGER NOT NULL DEFAULT 0,
    published_at TEXT NOT NULL DEFAULT '',
    published_by TEXT NOT NULL DEFAULT '',
    last_modified_at TEXT NOT NULL DEFAULT '',
    last_modified_by TEXT NOT NULL DEFAULT '',
    last_modified_source TEXT NOT NULL DEFAULT '',
    last_change_summary TEXT NOT NULL DEFAULT '',
    submitted_for_publish INTEGER NOT NULL DEFAULT 0,
    submitted_at TEXT NOT NULL DEFAULT '',
    submitted_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_agent_config_enabled
ON automation_agent_config (enabled, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_agent_config_updated
ON automation_agent_config (updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_agent_config_scenario
ON automation_agent_config (scenario_code, enabled, updated_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_agent_skill_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_code TEXT NOT NULL UNIQUE,
    agent_code TEXT NOT NULL DEFAULT '',
    pool_keys_json TEXT NOT NULL DEFAULT '[]',
    read_capabilities_json TEXT NOT NULL DEFAULT '[]',
    write_capabilities_json TEXT NOT NULL DEFAULT '[]',
    enabled INTEGER NOT NULL DEFAULT 1,
    input_schema_json TEXT NOT NULL DEFAULT '{}',
    output_schema_json TEXT NOT NULL DEFAULT '{}',
    permission_notes TEXT NOT NULL DEFAULT '',
    idempotency_notes TEXT NOT NULL DEFAULT '',
    audit_notes TEXT NOT NULL DEFAULT '',
    example_request_json TEXT NOT NULL DEFAULT '{}',
    example_response_json TEXT NOT NULL DEFAULT '{}',
    last_call_status TEXT NOT NULL DEFAULT 'never_called',
    last_error TEXT NOT NULL DEFAULT '',
    last_called_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_agent_skill_registry_enabled
ON automation_agent_skill_registry (enabled, updated_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_agent_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    request_id TEXT NOT NULL DEFAULT '',
    batch_id TEXT NOT NULL DEFAULT '',
    trace_id TEXT NOT NULL DEFAULT '',
    userid TEXT NOT NULL DEFAULT '',
    external_contact_id TEXT NOT NULL DEFAULT '',
    agent_code TEXT NOT NULL DEFAULT '',
    agent_type TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    input_snapshot_json TEXT NOT NULL DEFAULT '{}',
    variables_snapshot_json TEXT NOT NULL DEFAULT '{}',
    final_prompt_preview TEXT NOT NULL DEFAULT '',
    role_prompt_version TEXT NOT NULL DEFAULT '',
    task_prompt_version TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    error_code TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    latency_ms INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT '',
    parent_run_id TEXT NOT NULL DEFAULT '',
    replay_of_run_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_agent_run_request
ON automation_agent_run (request_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_agent_run_user
ON automation_agent_run (external_contact_id, userid, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_agent_run_agent_created
ON automation_agent_run (agent_code, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_agent_run_trace
ON automation_agent_run (trace_id, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_agent_output (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    output_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL DEFAULT '',
    request_id TEXT NOT NULL DEFAULT '',
    userid TEXT NOT NULL DEFAULT '',
    external_contact_id TEXT NOT NULL DEFAULT '',
    agent_code TEXT NOT NULL DEFAULT '',
    output_type TEXT NOT NULL DEFAULT '',
    raw_output_text TEXT NOT NULL DEFAULT '',
    normalized_output_json TEXT NOT NULL DEFAULT '{}',
    rendered_output_text TEXT NOT NULL DEFAULT '',
    target_agent_code TEXT NOT NULL DEFAULT '',
    target_pool TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    need_human_review INTEGER NOT NULL DEFAULT 0,
    applied_status TEXT NOT NULL DEFAULT 'pending',
    applied_at TEXT NOT NULL DEFAULT '',
    adopted_by TEXT NOT NULL DEFAULT '',
    adopted_action TEXT NOT NULL DEFAULT '',
    adopted_at TEXT NOT NULL DEFAULT '',
    outcome_status TEXT NOT NULL DEFAULT '',
    outcome_value TEXT NOT NULL DEFAULT '',
    revision_of_output_id TEXT NOT NULL DEFAULT '',
    error_code TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_agent_output_request
ON automation_agent_output (request_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_agent_output_user
ON automation_agent_output (external_contact_id, userid, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_agent_output_agent_type
ON automation_agent_output (agent_code, output_type, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_agent_output_applied
ON automation_agent_output (applied_status, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_agent_output_target_agent
ON automation_agent_output (target_agent_code, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_agent_output_outcome_status
ON automation_agent_output (outcome_status, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_agent_output_export_job (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL UNIQUE,
    requested_by TEXT NOT NULL DEFAULT '',
    filters_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'queued',
    total_count INTEGER NOT NULL DEFAULT 0,
    exported_count INTEGER NOT NULL DEFAULT 0,
    file_name TEXT NOT NULL DEFAULT '',
    file_content_base64 TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_automation_agent_output_export_job_status
ON automation_agent_output_export_job (status, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_agent_skill_call_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT NOT NULL UNIQUE,
    skill_code TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    permissions_scope TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL DEFAULT '',
    request_payload_json TEXT NOT NULL DEFAULT '{}',
    response_payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT '',
    error_code TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_agent_skill_call_audit_skill_created
ON automation_agent_skill_call_audit (skill_code, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_profile_segment_template (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id INTEGER,
    template_code TEXT NOT NULL UNIQUE,
    template_name TEXT NOT NULL DEFAULT '',
    questionnaire_id INTEGER REFERENCES questionnaires(id) ON DELETE SET NULL,
    segmentation_question_id INTEGER REFERENCES questionnaire_questions(id) ON DELETE SET NULL,
    description TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    version INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_profile_segment_template_enabled
ON automation_profile_segment_template (enabled, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_profile_segment_template_program
ON automation_profile_segment_template (program_id, enabled, updated_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_profile_segment_category (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL REFERENCES automation_profile_segment_template(id) ON DELETE CASCADE,
    category_key TEXT NOT NULL DEFAULT '',
    category_name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_profile_segment_category_template_key
ON automation_profile_segment_category (template_id, category_key);

CREATE INDEX IF NOT EXISTS idx_automation_profile_segment_category_template_sort
ON automation_profile_segment_category (template_id, sort_order ASC, id ASC);

CREATE TABLE IF NOT EXISTS automation_profile_segment_option_mapping (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL REFERENCES automation_profile_segment_template(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES automation_profile_segment_category(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES questionnaire_questions(id) ON DELETE CASCADE,
    option_id INTEGER NOT NULL REFERENCES questionnaire_options(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_profile_segment_option_mapping_unique
ON automation_profile_segment_option_mapping (category_id, question_id, option_id);

CREATE INDEX IF NOT EXISTS idx_automation_profile_segment_option_mapping_template
ON automation_profile_segment_option_mapping (template_id, question_id, option_id, id DESC);

CREATE TABLE IF NOT EXISTS automation_program (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_code TEXT NOT NULL UNIQUE,
    program_name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'paused', 'archived')),
    config_json TEXT NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_program_status
ON automation_program (status, updated_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_workflow (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id INTEGER REFERENCES automation_program(id) ON DELETE SET NULL,
    workflow_code TEXT NOT NULL UNIQUE,
    workflow_name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT 'approved',
    created_by_agent TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'paused', 'archived')),
    segmentation_basis TEXT NOT NULL DEFAULT 'none'
        CHECK (segmentation_basis IN ('none', 'profile', 'behavior')),
    generation_mode TEXT NOT NULL DEFAULT 'manual_layered'
        CHECK (generation_mode IN ('manual_layered', 'auto_layered_rewrite', 'personalized_single')),
    profile_segment_template_id INTEGER REFERENCES automation_profile_segment_template(id) ON DELETE SET NULL,
    behavior_tier_scheme TEXT NOT NULL DEFAULT 'fixed_v1',
    fallback_to_standard_content INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_workflow_status
ON automation_workflow (status, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_workflow_program
ON automation_workflow (program_id, status, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_workflow_enabled
ON automation_workflow (enabled, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_workflow_review
ON automation_workflow (review_status, status, updated_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_workflow_audience (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL REFERENCES automation_workflow(id) ON DELETE CASCADE,
    audience_code TEXT NOT NULL
        CHECK (audience_code IN ('pending_questionnaire', 'operating', 'converted')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_workflow_audience_unique
ON automation_workflow_audience (workflow_id, audience_code);

CREATE INDEX IF NOT EXISTS idx_automation_workflow_audience_code
ON automation_workflow_audience (audience_code, workflow_id);

CREATE TABLE IF NOT EXISTS automation_member_audience_entry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL REFERENCES automation_member(id) ON DELETE CASCADE,
    audience_code TEXT NOT NULL
        CHECK (audience_code IN ('pending_questionnaire', 'operating', 'converted')),
    entered_at TEXT NOT NULL DEFAULT '',
    exited_at TEXT NOT NULL DEFAULT '',
    is_current INTEGER NOT NULL DEFAULT 1,
    entry_source TEXT NOT NULL DEFAULT 'system',
    entry_reason TEXT NOT NULL DEFAULT '',
    source_snapshot_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_member_audience_entry_member_entered
ON automation_member_audience_entry (member_id, entered_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_member_audience_entry_audience_current
ON automation_member_audience_entry (audience_code, is_current, entered_at DESC, id DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_member_audience_entry_current
ON automation_member_audience_entry (member_id)
WHERE is_current = 1;

CREATE TABLE IF NOT EXISTS automation_workflow_agent_binding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL REFERENCES automation_workflow(id) ON DELETE CASCADE,
    node_id INTEGER REFERENCES automation_workflow_node(id) ON DELETE CASCADE,
    binding_scope TEXT NOT NULL DEFAULT 'default'
        CHECK (binding_scope IN ('default', 'profile_category', 'behavior_tier', 'personalized')),
    segment_key TEXT NOT NULL DEFAULT '',
    agent_code TEXT NOT NULL REFERENCES automation_agent_config(agent_code) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_workflow_agent_binding_unique
ON automation_workflow_agent_binding (workflow_id, COALESCE(node_id, 0), binding_scope, segment_key);

CREATE INDEX IF NOT EXISTS idx_automation_workflow_agent_binding_agent
ON automation_workflow_agent_binding (agent_code, updated_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_workflow_node (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL REFERENCES automation_workflow(id) ON DELETE CASCADE,
    node_code TEXT NOT NULL DEFAULT '',
    node_name TEXT NOT NULL DEFAULT '',
    target_audience_code TEXT NOT NULL
        CHECK (target_audience_code IN ('pending_questionnaire', 'operating', 'converted')),
    trigger_mode TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (trigger_mode IN ('scheduled', 'daily_recurring', 'audience_entered')),
    day_offset INTEGER NOT NULL DEFAULT 1,
    send_time TEXT NOT NULL DEFAULT '09:00',
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    position_index INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_workflow_node_code
ON automation_workflow_node (workflow_id, node_code);

CREATE INDEX IF NOT EXISTS idx_automation_workflow_node_position
ON automation_workflow_node (workflow_id, position_index ASC, id ASC);

CREATE INDEX IF NOT EXISTS idx_automation_workflow_node_schedule
ON automation_workflow_node (target_audience_code, day_offset, send_time, enabled, id ASC);

CREATE TABLE IF NOT EXISTS automation_workflow_node_content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id INTEGER NOT NULL UNIQUE REFERENCES automation_workflow_node(id) ON DELETE CASCADE,
    standard_content_text TEXT NOT NULL DEFAULT '',
    standard_content_payload_json TEXT NOT NULL DEFAULT '{}',
    fallback_to_standard_content INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS automation_workflow_node_content_variant (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_content_id INTEGER NOT NULL REFERENCES automation_workflow_node_content(id) ON DELETE CASCADE,
    variant_scope TEXT NOT NULL
        CHECK (variant_scope IN ('profile_category', 'behavior_tier', 'personalized')),
    segment_key TEXT NOT NULL DEFAULT '',
    content_text TEXT NOT NULL DEFAULT '',
    content_payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_workflow_node_content_variant_unique
ON automation_workflow_node_content_variant (node_content_id, variant_scope, segment_key);

CREATE INDEX IF NOT EXISTS idx_automation_workflow_node_content_variant_scope
ON automation_workflow_node_content_variant (variant_scope, segment_key, id DESC);

CREATE TABLE IF NOT EXISTS automation_workflow_execution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL UNIQUE,
    program_id INTEGER REFERENCES automation_program(id) ON DELETE SET NULL,
    workflow_id INTEGER REFERENCES automation_workflow(id) ON DELETE SET NULL,
    node_id INTEGER REFERENCES automation_workflow_node(id) ON DELETE SET NULL,
    trigger_type TEXT NOT NULL DEFAULT 'scheduled_poll'
        CHECK (trigger_type IN ('scheduled_poll', 'daily_recurring_poll', 'manual_replay', 'debug')),
    audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire'
        CHECK (audience_code IN ('pending_questionnaire', 'operating', 'converted')),
    scheduled_for TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'finished', 'partial_failed', 'failed')),
    total_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    summary_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_automation_workflow_execution_due
ON automation_workflow_execution (status, scheduled_for, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_workflow_execution_workflow
ON automation_workflow_execution (workflow_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_workflow_execution_program
ON automation_workflow_execution (program_id, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_workflow_execution_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id INTEGER NOT NULL REFERENCES automation_workflow_execution(id) ON DELETE CASCADE,
    workflow_id INTEGER REFERENCES automation_workflow(id) ON DELETE SET NULL,
    node_id INTEGER REFERENCES automation_workflow_node(id) ON DELETE SET NULL,
    member_id INTEGER REFERENCES automation_member(id) ON DELETE SET NULL,
    audience_entry_id INTEGER REFERENCES automation_member_audience_entry(id) ON DELETE SET NULL,
    external_contact_id TEXT NOT NULL DEFAULT '',
    rendered_content_text TEXT NOT NULL DEFAULT '',
    content_snapshot_json TEXT NOT NULL DEFAULT '{}',
    agent_code TEXT NOT NULL DEFAULT '',
    agent_run_id TEXT NOT NULL DEFAULT '',
    agent_output_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'prepared', 'sent', 'skipped', 'failed')),
    error_message TEXT NOT NULL DEFAULT '',
    last_error_text TEXT NOT NULL DEFAULT '',
    last_error_at TEXT NOT NULL DEFAULT '',
    retry_count INTEGER NOT NULL DEFAULT 0,
    trace_id TEXT NOT NULL DEFAULT '',
    next_node_id INTEGER,
    send_record_id INTEGER REFERENCES user_ops_send_records(id) ON DELETE SET NULL,
    sent_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_workflow_execution_item_execution
ON automation_workflow_execution_item (execution_id, id ASC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_workflow_execution_item_member_unique
ON automation_workflow_execution_item (execution_id, member_id);

CREATE INDEX IF NOT EXISTS idx_automation_workflow_execution_item_member
ON automation_workflow_execution_item (member_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_workflow_execution_item_send_record
ON automation_workflow_execution_item (send_record_id, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_focus_send_batch (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_automation_focus_send_batch_stage_status
ON automation_focus_send_batch (stage_key, status, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_focus_send_batch_due
ON automation_focus_send_batch (status, next_run_at, id ASC);

CREATE TABLE IF NOT EXISTS automation_focus_send_batch_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES automation_focus_send_batch(id) ON DELETE CASCADE,
    member_id INTEGER REFERENCES automation_member(id) ON DELETE SET NULL,
    external_contact_id TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    position_index INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    detail TEXT NOT NULL DEFAULT '',
    result_payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT NOT NULL DEFAULT '',
    finished_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_automation_focus_send_batch_item_batch_position
ON automation_focus_send_batch_item (batch_id, position_index ASC, id ASC);

CREATE INDEX IF NOT EXISTS idx_automation_focus_send_batch_item_status
ON automation_focus_send_batch_item (status, updated_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_touch_delivery_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_code TEXT NOT NULL DEFAULT 'signup_conversion_v1',
    touch_surface TEXT NOT NULL DEFAULT '',
    rule_key TEXT NOT NULL DEFAULT '',
    member_id INTEGER REFERENCES automation_member(id) ON DELETE SET NULL,
    external_contact_id TEXT NOT NULL DEFAULT '',
    source_batch_id INTEGER,
    source_item_id INTEGER,
    send_record_id INTEGER REFERENCES user_ops_send_records(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'claimed'
        CHECK (status IN ('claimed', 'sent', 'failed', 'skipped', 'cancelled')),
    detail TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    trace_id TEXT NOT NULL DEFAULT '',
    claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_touch_delivery_active
ON automation_touch_delivery_log (program_code, touch_surface, rule_key, external_contact_id)
WHERE external_contact_id <> '' AND status IN ('claimed', 'sent');

CREATE INDEX IF NOT EXISTS idx_automation_touch_delivery_external
ON automation_touch_delivery_log (external_contact_id, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_touch_delivery_source
ON automation_touch_delivery_log (touch_surface, source_batch_id, source_item_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_touch_delivery_trace
ON automation_touch_delivery_log (trace_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_touch_delivery_member_sent
ON automation_touch_delivery_log (member_id, sent_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_sop_pool_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_key TEXT NOT NULL UNIQUE CHECK (pool_key IN ('pending_questionnaire', 'operating', 'converted')),
    enabled INTEGER NOT NULL DEFAULT 1,
    max_day_count INTEGER NOT NULL DEFAULT 5,
    send_time TEXT NOT NULL DEFAULT '09:00',
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    effective_start_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_sop_pool_config_updated
ON automation_sop_pool_config (updated_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_sop_template (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_key TEXT NOT NULL DEFAULT '' CHECK (pool_key IN ('pending_questionnaire', 'operating', 'converted')),
    day_index INTEGER NOT NULL DEFAULT 1,
    content TEXT NOT NULL DEFAULT '',
    images_json TEXT NOT NULL DEFAULT '[]',
    miniprograms_json TEXT NOT NULL DEFAULT '[]',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_sop_template_pool_day
ON automation_sop_template (pool_key, day_index);

CREATE TABLE IF NOT EXISTS automation_sop_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL REFERENCES automation_member(id) ON DELETE CASCADE,
    pool_key TEXT NOT NULL DEFAULT '' CHECK (pool_key IN ('pending_questionnaire', 'operating', 'converted')),
    first_entered_at TEXT NOT NULL DEFAULT '',
    last_entered_at TEXT NOT NULL DEFAULT '',
    sop_anchor_date TEXT NOT NULL DEFAULT '',
    first_effective_in_pool_at TEXT NOT NULL DEFAULT '',
    last_in_pool_at TEXT NOT NULL DEFAULT '',
    last_sent_day INTEGER NOT NULL DEFAULT 0,
    last_sent_at TEXT NOT NULL DEFAULT '',
    completed_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_sop_progress_member_pool
ON automation_sop_progress (member_id, pool_key);

CREATE INDEX IF NOT EXISTS idx_automation_sop_progress_pool_day
ON automation_sop_progress (pool_key, last_sent_day, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_automation_sop_progress_pool_anchor
ON automation_sop_progress (pool_key, sop_anchor_date, updated_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS automation_sop_batch (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_key TEXT NOT NULL DEFAULT '' CHECK (pool_key IN ('pending_questionnaire', 'operating', 'converted')),
    day_index INTEGER NOT NULL DEFAULT 0,
    template_id INTEGER REFERENCES automation_sop_template(id) ON DELETE SET NULL,
    scheduled_for TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'empty',
    total_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    summary_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_sop_batch_status_scheduled
ON automation_sop_batch (status, scheduled_for, id DESC);

CREATE TABLE IF NOT EXISTS automation_sop_batch_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES automation_sop_batch(id) ON DELETE CASCADE,
    member_id INTEGER REFERENCES automation_member(id) ON DELETE CASCADE,
    pool_key TEXT NOT NULL DEFAULT '' CHECK (pool_key IN ('pending_questionnaire', 'operating', 'converted')),
    day_index INTEGER NOT NULL DEFAULT 0,
    day_index_snapshot INTEGER NOT NULL DEFAULT 0,
    external_userid TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'skipped',
    error_message TEXT NOT NULL DEFAULT '',
    content_snapshot TEXT NOT NULL DEFAULT '',
    images_snapshot TEXT NOT NULL DEFAULT '[]',
    sent_record_id INTEGER REFERENCES user_ops_send_records(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_sop_batch_item_batch_created
ON automation_sop_batch_item (batch_id, id ASC);

CREATE INDEX IF NOT EXISTS idx_automation_sop_batch_item_member_day_snapshot
ON automation_sop_batch_item (member_id, pool_key, day_index_snapshot, id DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_sop_batch_item_member_pool_day_success
ON automation_sop_batch_item (member_id, pool_key, day_index)
WHERE status = 'success';

CREATE INDEX IF NOT EXISTS idx_conversion_dispatch_log_external_dispatched
ON conversion_dispatch_log (external_userid, dispatched_at DESC);

CREATE TABLE IF NOT EXISTS automation_execution_trace (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    workflow_node_id TEXT,
    external_userid TEXT,
    member_id INTEGER,
    decision_point TEXT NOT NULL,
    decision_outcome TEXT NOT NULL,
    reason TEXT,
    request_id TEXT,
    job_id TEXT,
    parent_request_id TEXT,
    payload_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_execution_trace_workflow
ON automation_execution_trace (workflow_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_automation_execution_trace_external
ON automation_execution_trace (external_userid, created_at DESC);

CREATE TABLE IF NOT EXISTS outbound_event_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    target_name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    idempotency_key TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    last_error TEXT,
    request_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_outbound_event_outbox_status_next
ON outbound_event_outbox (status, next_attempt_at);

CREATE INDEX IF NOT EXISTS idx_outbound_event_outbox_idempotency
ON outbound_event_outbox (idempotency_key);

-- ============================================================================
-- Cloud orchestrator + journey cadence + frequency budget (revision 0004)
-- ============================================================================

CREATE TABLE IF NOT EXISTS automation_workflow_goal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL,
    goal_code TEXT NOT NULL,
    goal_label TEXT NOT NULL DEFAULT '',
    success_event_action TEXT NOT NULL DEFAULT '',
    weight INTEGER NOT NULL DEFAULT 100,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_workflow_goal
ON automation_workflow_goal (workflow_id, goal_code);

CREATE INDEX IF NOT EXISTS idx_automation_workflow_goal_workflow
ON automation_workflow_goal (workflow_id, enabled, weight DESC, id ASC);

CREATE TABLE IF NOT EXISTS automation_workflow_node_transition (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node_id INTEGER NOT NULL,
    to_node_id INTEGER,
    condition_kind TEXT NOT NULL DEFAULT 'reply_received',
    condition_payload_json TEXT NOT NULL DEFAULT '{}',
    action TEXT NOT NULL DEFAULT 'goto_node',
    priority INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_workflow_node_transition_from
ON automation_workflow_node_transition (from_node_id, enabled, priority DESC, id ASC);

CREATE TABLE IF NOT EXISTS automation_frequency_budget (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    budget_code TEXT NOT NULL UNIQUE,
    scope TEXT NOT NULL DEFAULT 'global',
    scope_key TEXT NOT NULL DEFAULT '',
    window_seconds INTEGER NOT NULL DEFAULT 604800,
    max_count INTEGER NOT NULL DEFAULT 3,
    description TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_frequency_budget_enabled
ON automation_frequency_budget (enabled, scope, scope_key, id ASC);

CREATE TABLE IF NOT EXISTS automation_frequency_consumption (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    budget_id INTEGER NOT NULL,
    member_id INTEGER,
    external_contact_id TEXT NOT NULL DEFAULT '',
    consumed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_kind TEXT NOT NULL DEFAULT '',
    source_id TEXT NOT NULL DEFAULT '',
    trace_id TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_automation_frequency_consumption_member_window
ON automation_frequency_consumption (member_id, budget_id, consumed_at DESC);

CREATE INDEX IF NOT EXISTS idx_automation_frequency_consumption_external_window
ON automation_frequency_consumption (external_contact_id, budget_id, consumed_at DESC);

CREATE INDEX IF NOT EXISTS idx_automation_frequency_consumption_trace
ON automation_frequency_consumption (trace_id, id ASC);

CREATE TABLE IF NOT EXISTS cloud_broadcast_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id TEXT NOT NULL UNIQUE,
    trace_id TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    operator TEXT NOT NULL DEFAULT '',
    intent TEXT NOT NULL DEFAULT '',
    segment_id INTEGER,
    campaign_id INTEGER,
    selection_json TEXT NOT NULL DEFAULT '{}',
    content_strategy TEXT NOT NULL DEFAULT 'profile_layered',
    content_template TEXT NOT NULL DEFAULT '',
    personalization_json TEXT NOT NULL DEFAULT '[]',
    max_recipients INTEGER NOT NULL DEFAULT 0,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    explanation_json TEXT NOT NULL DEFAULT '{}',
    variants_json TEXT NOT NULL DEFAULT '[]',
    copy_workorder_run_ids TEXT NOT NULL DEFAULT '[]',
    requires_manual_copy INTEGER NOT NULL DEFAULT 0,
    attachments_json TEXT NOT NULL DEFAULT '[]',
    simulate_summary_json TEXT NOT NULL DEFAULT '{}',
    commit_batch_id TEXT NOT NULL DEFAULT '',
    commit_send_record_id INTEGER,
    committed_at TEXT NOT NULL DEFAULT '',
    committed_by TEXT NOT NULL DEFAULT '',
    approval_token_hash TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    error_message TEXT NOT NULL DEFAULT '',
    expires_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cloud_broadcast_plans_status
ON cloud_broadcast_plans (status, expires_at, id DESC);

CREATE INDEX IF NOT EXISTS idx_cloud_broadcast_plans_trace
ON cloud_broadcast_plans (trace_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_cloud_broadcast_plans_session
ON cloud_broadcast_plans (session_id, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS cloud_agent_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL DEFAULT '',
    trace_id TEXT NOT NULL DEFAULT '',
    operator TEXT NOT NULL DEFAULT '',
    tool_name TEXT NOT NULL DEFAULT '',
    arguments_hash TEXT NOT NULL DEFAULT '',
    arguments_json TEXT NOT NULL DEFAULT '{}',
    result_summary TEXT NOT NULL DEFAULT '',
    latency_ms INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'success',
    error_message TEXT NOT NULL DEFAULT '',
    requires_token INTEGER NOT NULL DEFAULT 0,
    token_verified INTEGER NOT NULL DEFAULT 0,
    full_payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cloud_agent_audit_log_session
ON cloud_agent_audit_log (session_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_cloud_agent_audit_log_trace
ON cloud_agent_audit_log (trace_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_cloud_agent_audit_log_tool
ON cloud_agent_audit_log (tool_name, status, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS cloud_approval_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    plan_id TEXT NOT NULL DEFAULT '',
    operator TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT 'commit_broadcast_plan',
    issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT NOT NULL DEFAULT '',
    consumed_at TEXT NOT NULL DEFAULT '',
    consumed_by TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_cloud_approval_tokens_plan
ON cloud_approval_tokens (plan_id, issued_at DESC, id DESC);

-- ============================================================================
-- Segments registry + Campaigns (revision 0005)
-- ============================================================================

CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'ai_generated',
    sql_query TEXT NOT NULL DEFAULT '',
    sql_params_json TEXT NOT NULL DEFAULT '{}',
    sql_dialect TEXT NOT NULL DEFAULT 'sqlite',
    status TEXT NOT NULL DEFAULT 'draft',
    version INTEGER NOT NULL DEFAULT 1,
    created_by_agent TEXT NOT NULL DEFAULT '',
    created_by_session TEXT NOT NULL DEFAULT '',
    cached_headcount INTEGER NOT NULL DEFAULT 0,
    cached_sample_json TEXT NOT NULL DEFAULT '[]',
    last_refreshed_at TEXT NOT NULL DEFAULT '',
    last_refresh_error TEXT NOT NULL DEFAULT '',
    usage_count INTEGER NOT NULL DEFAULT 0,
    tags_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_segments_status_source
ON segments (status, source_type, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_segments_usage
ON segments (usage_count DESC, last_refreshed_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS segment_member_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    external_contact_id TEXT NOT NULL DEFAULT '',
    captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_segment_member_snapshots_segment
ON segment_member_snapshots (segment_id, captured_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_segment_member_snapshots_member
ON segment_member_snapshots (member_id, captured_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL DEFAULT '',
    intent TEXT NOT NULL DEFAULT '',
    anchor_mode TEXT NOT NULL DEFAULT 'campaign_start_date',
    anchor_date TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT 'pending_review',
    run_status TEXT NOT NULL DEFAULT 'draft',
    created_by_agent TEXT NOT NULL DEFAULT '',
    created_by_session TEXT NOT NULL DEFAULT '',
    trace_id TEXT NOT NULL DEFAULT '',
    owner_userid TEXT NOT NULL DEFAULT '',
    approval_token_hash TEXT NOT NULL DEFAULT '',
    approved_by TEXT NOT NULL DEFAULT '',
    approved_at TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT '',
    finished_at TEXT NOT NULL DEFAULT '',
    paused_at TEXT NOT NULL DEFAULT '',
    paused_reason TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    stats_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_campaigns_review
ON campaigns (review_status, run_status, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_campaigns_run_status
ON campaigns (run_status, anchor_date, id DESC);

CREATE INDEX IF NOT EXISTS idx_campaigns_trace
ON campaigns (trace_id, id DESC);

CREATE TABLE IF NOT EXISTS campaign_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    segment_id INTEGER NOT NULL,
    segment_code TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL DEFAULT 100,
    label TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_campaign_segments_unique
ON campaign_segments (campaign_id, segment_id);

CREATE INDEX IF NOT EXISTS idx_campaign_segments_priority
ON campaign_segments (campaign_id, priority DESC, id ASC);

CREATE TABLE IF NOT EXISTS campaign_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    campaign_segment_id INTEGER NOT NULL,
    step_index INTEGER NOT NULL DEFAULT 0,
    day_offset INTEGER NOT NULL DEFAULT 0,
    send_time TEXT NOT NULL DEFAULT '09:00',
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    content_text TEXT NOT NULL DEFAULT '',
    content_payload_json TEXT NOT NULL DEFAULT '{}',
    stop_on_reply INTEGER NOT NULL DEFAULT 1,
    skip_if_recently_touched_days INTEGER NOT NULL DEFAULT 0,
    agent_run_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_campaign_steps_unique
ON campaign_steps (campaign_segment_id, step_index);

CREATE INDEX IF NOT EXISTS idx_campaign_steps_due
ON campaign_steps (campaign_id, day_offset ASC, step_index ASC);

-- 关键互斥保障：UNIQUE(campaign_id, member_id) — 一个用户在同一 Campaign 内只占一行
CREATE TABLE IF NOT EXISTS campaign_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    campaign_segment_id INTEGER NOT NULL,
    segment_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    external_contact_id TEXT NOT NULL DEFAULT '',
    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    anchor_date TEXT NOT NULL DEFAULT '',
    current_step_index INTEGER NOT NULL DEFAULT -1,
    next_due_at TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    stop_reason TEXT NOT NULL DEFAULT '',
    last_step_sent_at TEXT NOT NULL DEFAULT '',
    last_error_text TEXT NOT NULL DEFAULT '',
    retry_count INTEGER NOT NULL DEFAULT 0,
    trace_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_campaign_members_one_per_campaign
ON campaign_members (campaign_id, member_id);

CREATE INDEX IF NOT EXISTS idx_campaign_members_due
ON campaign_members (status, next_due_at, id ASC);

CREATE INDEX IF NOT EXISTS idx_campaign_members_segment
ON campaign_members (campaign_segment_id, status, id ASC);

CREATE INDEX IF NOT EXISTS idx_campaign_members_external
ON campaign_members (external_contact_id, campaign_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_campaign_members_trace
ON campaign_members (trace_id, id DESC);

DROP VIEW IF EXISTS automation_member_interaction_stats;
CREATE VIEW automation_member_interaction_stats AS
SELECT
    m.id AS member_id,
    m.external_contact_id,
    m.phone,
    m.current_pool,
    m.current_audience_code,
    m.profile_segment_key,
    m.behavior_tier_key,
    m.last_ai_push_at,
    m.ai_cooldown_until,
    (
        SELECT MAX(sent_at) FROM automation_touch_delivery_log d
        WHERE d.member_id = m.id AND d.status = 'sent'
    ) AS last_outbound_at,
    (
        SELECT COUNT(*) FROM automation_touch_delivery_log d
        WHERE d.member_id = m.id AND d.status = 'sent'
    ) AS outbound_count_total,
    (
        SELECT COUNT(*) FROM automation_touch_delivery_log d
        WHERE d.member_id = m.id AND d.status = 'sent'
          AND d.sent_at >= datetime('now', '-7 days')
    ) AS outbound_count_7d,
    (
        SELECT COUNT(*) FROM automation_touch_delivery_log d
        WHERE d.member_id = m.id AND d.status = 'sent'
          AND d.sent_at >= datetime('now', '-30 days')
    ) AS outbound_count_30d,
    (
        SELECT MAX(pushed_at) FROM automation_ai_push_log p
        WHERE p.member_id = m.id
    ) AS last_ai_push_log_at,
    (
        SELECT COUNT(*) FROM automation_ai_push_log p
        WHERE p.member_id = m.id
          AND p.pushed_at >= datetime('now', '-30 days')
    ) AS ai_push_count_30d
FROM automation_member m;

CREATE TABLE IF NOT EXISTS miniprogram_library (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT '',
    appid TEXT NOT NULL,
    pagepath TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    thumb_image_url TEXT NOT NULL DEFAULT '',
    thumb_image_base64 TEXT NOT NULL DEFAULT '',
    thumb_image_id INTEGER,
    thumb_media_id TEXT NOT NULL DEFAULT '',
    thumb_media_id_expires_at TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_miniprogram_library_enabled
ON miniprogram_library (enabled, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_miniprogram_library_appid
ON miniprogram_library (appid, id DESC);

CREATE TABLE IF NOT EXISTS image_library (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT '',
    file_name TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'upload',
    source_url TEXT NOT NULL DEFAULT '',
    data_base64 TEXT NOT NULL DEFAULT '',
    mime_type TEXT NOT NULL DEFAULT 'image/png',
    file_size INTEGER NOT NULL DEFAULT 0,
    thumb_media_id TEXT NOT NULL DEFAULT '',
    thumb_media_id_expires_at TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_image_library_enabled
ON image_library (enabled, updated_at DESC, id DESC);

-- broadcast_jobs — 统一群发任务队列（revision 0008，SQLite 版）

CREATE TABLE IF NOT EXISTS broadcast_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL DEFAULT ''
        CHECK (source_type IN ('campaign', 'sop', 'workflow', 'cloud_plan', 'focus_send', 'deferred', 'manual')),
    source_id TEXT NOT NULL DEFAULT '',
    source_table TEXT NOT NULL DEFAULT '',
    scheduled_for TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    priority INTEGER NOT NULL DEFAULT 100,
    batch_key TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('waiting_approval', 'queued', 'claimed', 'sent', 'failed', 'cancelled')),
    requires_approval INTEGER NOT NULL DEFAULT 0,
    approved_by TEXT NOT NULL DEFAULT '',
    approved_at TEXT,
    cancelled_by TEXT NOT NULL DEFAULT '',
    cancelled_at TEXT,
    cancel_reason TEXT NOT NULL DEFAULT '',
    target_external_userids TEXT NOT NULL DEFAULT '[]',
    target_count INTEGER NOT NULL DEFAULT 0,
    target_summary TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL DEFAULT 'text',
    content_payload TEXT NOT NULL DEFAULT '{}',
    content_summary TEXT NOT NULL DEFAULT '',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    outbound_task_id INTEGER,
    sent_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    trace_id TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_at TEXT,
    sent_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_broadcast_jobs_due
ON broadcast_jobs (status, scheduled_for, priority, id ASC);

CREATE INDEX IF NOT EXISTS idx_broadcast_jobs_timeline
ON broadcast_jobs (scheduled_for DESC, status, id DESC);

CREATE INDEX IF NOT EXISTS idx_broadcast_jobs_source
ON broadcast_jobs (source_type, source_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_broadcast_jobs_trace
ON broadcast_jobs (trace_id, id DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_broadcast_jobs_source_scheduled
ON broadcast_jobs (source_table, source_id, scheduled_for);
