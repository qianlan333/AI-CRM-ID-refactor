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
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_questionnaires_slug
ON questionnaires (slug);

CREATE INDEX IF NOT EXISTS idx_questionnaires_disabled
ON questionnaires (is_disabled);

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
