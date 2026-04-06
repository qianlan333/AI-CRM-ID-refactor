from __future__ import annotations

from typing import Any

from .domains.archive import repo as archive_repo
from .domains.archive import service as archive_domain_service
from .domains.callbacks import service as callbacks_domain_service
from .domains.class_user import service as class_user_domain_service
from .domains.contacts import repo as contacts_repo
from .domains.contacts import service as contacts_domain_service
from .domains.group_chats import repo as group_chat_repo
from .domains.group_chats import service as group_chat_domain_service
from .domains.identity import service as identity_domain_service
from .domains.marketing_automation import service as marketing_automation_domain_service
from .domains.outbound_webhook import service as outbound_webhook_domain_service
from .domains.questionnaire import service as questionnaire_domain_service
from .domains.routing_config.service import (
    build_routing_config as _build_routing_config,
    get_owner_class_term_backfill_entry_source_override,
    get_owner_role as _get_owner_role,
    list_owner_role_map as _list_owner_role_map,
    resolve_contact_routing_context as _resolve_contact_routing_context,
)
from .domains.tags import repo as tags_repo
from .domains.tags import service as tags_domain_service
from .domains.tasks import service as tasks_domain_service
from .domains.user_ops import page_service as user_ops_page_service
from .domains.user_ops import service as user_ops_domain_service
from .infra.helpers import (
    db_bool as _db_bool,
    normalize_optional_timestamp as _normalize_optional_timestamp,
    stringify_db_timestamp as _stringify_db_timestamp,
)
from .infra.wecom_runtime import get_contact_runtime_client


# Thin compatibility facade:
# - re-export stable helpers from domain/infra modules
# - keep a small number of wrappers where backward-compatible call signatures,
#   dependency injection, or monkeypatch points still matter
# - do not place new domain implementation here

QUESTIONNAIRE_TYPES = questionnaire_domain_service.QUESTIONNAIRE_TYPES
questionnaire_logger = questionnaire_domain_service.questionnaire_logger
owner_backfill_logger = user_ops_domain_service.owner_backfill_logger

QuestionnaireAlreadySubmittedError = questionnaire_domain_service.QuestionnaireAlreadySubmittedError
ContactBindingConflictError = identity_domain_service.ContactBindingConflictError
ThirdPartyUserSyncError = user_ops_domain_service.ThirdPartyUserSyncError

_select_follow_user = contacts_domain_service._select_follow_user
_parse_send_time = archive_repo._parse_send_time
_batch_window_for_send_time = archive_repo._batch_window_for_send_time

normalize_contact_record = contacts_domain_service.normalize_contact_record
target_contact_description = contacts_domain_service.target_contact_description
contact_description_state = contacts_domain_service.contact_description_state
needs_contact_description_update = contacts_domain_service.needs_contact_description_update
plan_contact_description_fix = contacts_domain_service.plan_contact_description_fix
upsert_contacts = contacts_repo.upsert_contacts
list_contacts = contacts_repo.list_contacts
get_contact_tag_snapshots = tags_repo.get_contact_tag_snapshots
get_owner_role = _get_owner_role
list_owner_role_map = _list_owner_role_map
list_signup_tag_rules = tags_repo.list_signup_tag_rules
_signup_tag_group_name = tags_domain_service.signup_tag_group_name
get_signup_status_definitions = tags_domain_service.get_signup_status_definitions
get_signup_status_definition = tags_domain_service.get_signup_status_definition
get_signup_status_definition_by_tag_name = tags_domain_service.get_signup_status_definition_by_tag_name
upsert_signup_tag_rule = tags_repo.upsert_signup_tag_rule
get_signup_tag_rules_config = tags_domain_service.get_signup_tag_rules_config
resolve_signup_status_from_tags = tags_domain_service.resolve_signup_status_from_tags
build_class_user_tag_view = tags_domain_service.build_class_user_tag_view

get_class_user_status_definition = class_user_domain_service.get_class_user_status_definition
get_class_user_status_current = class_user_domain_service.get_class_user_status_current
upsert_class_user_status_current = class_user_domain_service.upsert_class_user_status_current
append_class_user_status_history = class_user_domain_service.append_class_user_status_history
update_class_user_status_sync_result = class_user_domain_service.update_class_user_status_sync_result
list_class_user_status_history = class_user_domain_service.list_class_user_status_history
apply_class_user_status_change = class_user_domain_service.apply_class_user_status_change

update_contact_description_snapshot = contacts_repo.update_contact_description_snapshot
count_contacts = contacts_repo.count_contacts
get_last_contacts_sync_time = contacts_repo.get_last_contacts_sync_time

normalize_external_contact_identity = identity_domain_service.normalize_external_contact_identity
replace_external_contact_follow_users = identity_domain_service.replace_external_contact_follow_users
mark_external_contact_follow_user_status = identity_domain_service.mark_external_contact_follow_user_status
refresh_external_contact_identity_owner = identity_domain_service.refresh_external_contact_identity_owner
upsert_external_contact_identity = identity_domain_service.upsert_external_contact_identity
mark_external_contact_identity_status = identity_domain_service.mark_external_contact_identity_status
count_external_contact_identity_maps = identity_domain_service.count_external_contact_identity_maps
resolve_external_contact_identity = identity_domain_service.resolve_external_contact_identity
bind_openid_to_external_contact = identity_domain_service.bind_openid_to_external_contact
_normalize_mobile = identity_domain_service.normalize_mobile

_normalize_legacy_user_ops_current_status = user_ops_domain_service._normalize_legacy_user_ops_current_status
_legacy_user_ops_status_rank = user_ops_domain_service._legacy_user_ops_status_rank
_user_ops_merge_key = user_ops_domain_service._user_ops_merge_key
_extract_third_party_user_id = user_ops_domain_service._extract_third_party_user_id
_user_ops_resolve_third_party_user_id_by_mobile_impl = user_ops_domain_service._resolve_third_party_user_id_by_mobile
_normalize_user_ops_lead_pool_activation_state = user_ops_domain_service._normalize_user_ops_lead_pool_activation_state
_serialize_user_ops_lead_pool_current_row = user_ops_domain_service._serialize_user_ops_lead_pool_current_row
_get_user_ops_lead_pool_current_row_by_id = user_ops_domain_service._get_user_ops_lead_pool_current_row_by_id
_list_user_ops_lead_pool_matches = user_ops_domain_service._list_user_ops_lead_pool_matches
_current_user_ops_operator = user_ops_domain_service._current_user_ops_operator
_user_ops_class_term_options = user_ops_domain_service._user_ops_class_term_options
_get_active_class_term_mapping_by_no = user_ops_domain_service._get_active_class_term_mapping_by_no

log_external_contact_event = callbacks_domain_service.log_external_contact_event
mark_external_contact_event_processing = callbacks_domain_service.mark_external_contact_event_processing
get_external_contact_event_log = callbacks_domain_service.get_external_contact_event_log
finish_external_contact_event_log = callbacks_domain_service.finish_external_contact_event_log
get_recent_external_contact_event_logs = callbacks_domain_service.get_recent_external_contact_event_logs

normalize_group_chat_record = group_chat_domain_service.normalize_group_chat_record
upsert_group_chats = group_chat_repo.upsert_group_chats
get_group_chat_by_chat_id = group_chat_repo.get_group_chat_by_chat_id
get_group_chat_map = group_chat_repo.get_group_chat_map
list_group_chats = group_chat_repo.list_group_chats
count_group_chats = group_chat_repo.count_group_chats

count_archived_messages = archive_domain_service.count_archived_messages
normalize_archived_message = archive_domain_service.normalize_archived_message
format_message_row = archive_domain_service.format_message_row
extract_roomid_from_raw_payload = archive_domain_service.extract_roomid_from_raw_payload
insert_archived_messages = archive_domain_service.insert_archived_messages
create_sync_run = archive_domain_service.create_sync_run
finish_sync_run = archive_domain_service.finish_sync_run
_normalize_chat_type_filter = archive_domain_service._normalize_chat_type_filter
list_archived_messages_by_window = archive_domain_service.list_archived_messages_by_window
get_archive_last_seq = archive_domain_service.get_archive_last_seq
set_archive_last_seq = archive_domain_service.set_archive_last_seq
get_last_sync_run = archive_domain_service.get_last_sync_run
materialize_message_batches = archive_domain_service.materialize_message_batches
list_message_batches = archive_domain_service.list_message_batches
ack_message_batch = archive_domain_service.ack_message_batch

save_outbound_task = tasks_domain_service.save_outbound_task
record_conversion_feedback = tasks_domain_service.record_conversion_feedback
ack_conversion_batch = marketing_automation_domain_service.ack_conversion_batch
apply_activation_webhook = marketing_automation_domain_service.apply_activation_webhook
get_conversion_batch = marketing_automation_domain_service.get_conversion_batch
get_customer_marketing_profile = marketing_automation_domain_service.get_customer_marketing_profile
get_customer_trial_opening_fact = marketing_automation_domain_service.get_customer_trial_opening_fact
evaluate_customer_marketing_state = marketing_automation_domain_service.evaluate_customer_marketing_state
evaluate_customer_value_segment = marketing_automation_domain_service.evaluate_customer_value_segment
get_openclaw_customer_marketing_profile = marketing_automation_domain_service.get_openclaw_customer_marketing_profile
get_pending_conversion_batches = marketing_automation_domain_service.get_pending_conversion_batches
process_inbound_messages_for_openclaw = marketing_automation_domain_service.process_inbound_messages_for_openclaw
send_pool_private_message = marketing_automation_domain_service.send_pool_private_message
list_outbound_webhook_deliveries = outbound_webhook_domain_service.list_outbound_webhook_deliveries
get_outbound_webhook_delivery_counts = outbound_webhook_domain_service.get_outbound_webhook_delivery_counts
get_signup_conversion_config = marketing_automation_domain_service.get_signup_conversion_config
list_signup_conversion_batches = marketing_automation_domain_service.list_signup_conversion_batches
get_signup_conversion_batch = marketing_automation_domain_service.get_signup_conversion_batch
route_signup_conversion_batch_candidates = marketing_automation_domain_service.route_signup_conversion_batch_candidates
list_signup_conversion_question_rules = marketing_automation_domain_service.list_signup_conversion_question_rules
mark_enrolled = marketing_automation_domain_service.mark_enrolled
preview_signup_conversion_customer = marketing_automation_domain_service.preview_signup_conversion_customer
recompute_signup_conversion_customers = marketing_automation_domain_service.recompute_signup_conversion_customers
save_signup_conversion_config = marketing_automation_domain_service.save_signup_conversion_config
set_manual_followup_segment = marketing_automation_domain_service.set_manual_followup_segment
trigger_openclaw_focus_message_webhook = marketing_automation_domain_service.trigger_openclaw_focus_message_webhook
unmark_enrolled = marketing_automation_domain_service.unmark_enrolled
upsert_customer_trial_opening_fact = marketing_automation_domain_service.upsert_customer_trial_opening_fact
retry_outbound_webhook_delivery = outbound_webhook_domain_service.retry_outbound_webhook_delivery
run_due_outbound_webhook_retries = outbound_webhook_domain_service.run_due_outbound_webhook_retries

save_tag_snapshot = tags_repo.save_tag_snapshot
remove_tag_snapshot = tags_repo.remove_tag_snapshot
remove_tag_snapshots_for_other_users = tags_repo.remove_tag_snapshots_for_other_users
_list_contact_tag_ids_for_user = tags_repo.list_contact_tag_ids_for_user
remove_all_tag_snapshots_for_other_users = tags_repo.remove_all_tag_snapshots_for_other_users

_json_dumps = questionnaire_domain_service._json_dumps
_json_array = questionnaire_domain_service._json_array
_dedupe_strings = questionnaire_domain_service._dedupe_strings
_normalize_bool = questionnaire_domain_service._normalize_bool
_normalize_float = questionnaire_domain_service._normalize_float
_normalize_int = questionnaire_domain_service._normalize_int
_normalize_required_integer = questionnaire_domain_service._normalize_required_integer
_validate_tag_codes_payload = questionnaire_domain_service._validate_tag_codes_payload
_slugify_questionnaire = questionnaire_domain_service._slugify_questionnaire
_normalize_tag_codes = questionnaire_domain_service._normalize_tag_codes
list_questionnaires = questionnaire_domain_service.list_questionnaires
list_available_wecom_tags = questionnaire_domain_service.list_available_wecom_tags
get_latest_questionnaire_submit_debug = questionnaire_domain_service.get_latest_questionnaire_submit_debug
create_questionnaire = questionnaire_domain_service.create_questionnaire
get_questionnaire_detail = questionnaire_domain_service.get_questionnaire_detail
update_questionnaire = questionnaire_domain_service.update_questionnaire
disable_questionnaire = questionnaire_domain_service.disable_questionnaire
delete_questionnaire = questionnaire_domain_service.delete_questionnaire
export_questionnaire_submissions = questionnaire_domain_service.export_questionnaire_submissions
get_public_questionnaire_by_slug = questionnaire_domain_service.get_public_questionnaire_by_slug
validate_questionnaire_answers = questionnaire_domain_service.validate_questionnaire_answers
compute_questionnaire_result = questionnaire_domain_service.compute_questionnaire_result


def _bind_questionnaire_domain() -> None:
    questionnaire_domain_service.QuestionnaireAlreadySubmittedError = QuestionnaireAlreadySubmittedError
    questionnaire_domain_service.resolve_external_contact_identity = resolve_external_contact_identity
    questionnaire_domain_service.bind_openid_to_external_contact = bind_openid_to_external_contact
    questionnaire_domain_service.bind_mobile_to_external_contact = bind_mobile_to_external_contact
    questionnaire_domain_service._normalize_mobile = _normalize_mobile


def _user_ops_contact_client():
    return get_contact_runtime_client()


def _bind_user_ops_domain() -> None:
    user_ops_domain_service._user_ops_contact_client = _user_ops_contact_client
    user_ops_domain_service._resolve_third_party_user_id_by_mobile = _resolve_third_party_user_id_by_mobile
    user_ops_domain_service._db_bool = _db_bool
    user_ops_domain_service._normalize_mobile = _normalize_mobile
    user_ops_domain_service._list_contact_tag_ids_for_user = _list_contact_tag_ids_for_user
    user_ops_domain_service._stringify_db_timestamp = _stringify_db_timestamp
    user_ops_domain_service.resolve_person_identity = resolve_person_identity
    user_ops_domain_service.get_contact_binding_status = get_contact_binding_status
    user_ops_domain_service.save_tag_snapshot = save_tag_snapshot
    user_ops_domain_service.remove_tag_snapshot = remove_tag_snapshot
    user_ops_domain_service.remove_tag_snapshots_for_other_users = remove_tag_snapshots_for_other_users
    user_ops_domain_service.remove_all_tag_snapshots_for_other_users = remove_all_tag_snapshots_for_other_users
    user_ops_domain_service.get_owner_class_term_backfill_entry_source_override = (
        get_owner_class_term_backfill_entry_source_override
    )
    user_ops_domain_service.get_signup_status_definition_by_tag_name = get_signup_status_definition_by_tag_name
    user_ops_domain_service.get_class_user_status_definition = get_class_user_status_definition
    user_ops_domain_service.get_class_user_status_current = get_class_user_status_current
    user_ops_domain_service.upsert_class_user_status_current = upsert_class_user_status_current
    user_ops_domain_service.append_class_user_status_history = append_class_user_status_history
    user_ops_domain_service.update_class_user_status_sync_result = update_class_user_status_sync_result


def _resolve_signup_status_for_contact(external_userid: str, owner_userid: str) -> str:
    payload = enrich_contact_context(
        {
            "external_userid": str(external_userid or "").strip(),
            "owner_userid": str(owner_userid or "").strip(),
        }
    )
    return str(payload.get("signup_status") or "").strip()


def get_routing_config() -> dict[str, Any]:
    return _build_routing_config(
        owner_role_map=list_owner_role_map(active_only=True),
        signup_tag_rules=get_signup_tag_rules_config(),
    )


def resolve_contact_routing_context(owner_userid: str, owner_role: str, signup_status: str) -> dict[str, Any]:
    definition = get_signup_status_definition(signup_status)
    return _resolve_contact_routing_context(
        owner_userid=owner_userid,
        owner_role=owner_role,
        signup_status=signup_status,
        routing_alias=str(definition.get("routing_alias") or "") if definition else "",
    )


def enrich_contact_context(contact: dict[str, Any]) -> dict[str, Any]:
    return contacts_domain_service.enrich_contact_context(
        contact,
        get_owner_role=get_owner_role,
        get_contact_tag_snapshots=get_contact_tag_snapshots,
        resolve_signup_status_from_tags=resolve_signup_status_from_tags,
        resolve_contact_routing_context=resolve_contact_routing_context,
    )


def get_contact_by_external_userid(external_userid: str, *, refresh_tags: bool = False) -> dict[str, Any] | None:
    return contacts_domain_service.get_contact_by_external_userid(
        external_userid,
        refresh_tags=refresh_tags,
        refresh_contact_tags_for_external_userid=refresh_contact_tags_for_external_userid,
        enrich_contact_context=enrich_contact_context,
    )


def get_primary_follow_user_userid(external_userid: str) -> str:
    return identity_domain_service.get_primary_follow_user_userid(
        external_userid,
        active_value=_db_bool(True),
        contact_loader=get_contact_by_external_userid,
        resolve_identity=lambda corp_id, value: resolve_external_contact_identity(corp_id, external_userid=value),
    )


def get_class_user_snapshot(external_userid: str, owner_userid: str = "") -> dict[str, str]:
    return class_user_domain_service.get_class_user_snapshot(
        external_userid,
        owner_userid,
        contact_loader=lambda value: get_contact_by_external_userid(value),
        person_identity_resolver=lambda **kwargs: resolve_person_identity(**kwargs),
    )


def list_class_user_management_records(signup_status: str = "") -> dict[str, Any]:
    return class_user_domain_service.list_class_user_management_records(
        signup_status=signup_status,
        get_signup_status_definitions=get_signup_status_definitions,
    )


def export_class_user_management_records(signup_status: str = "") -> dict[str, Any]:
    return class_user_domain_service.export_class_user_management_records(
        signup_status=signup_status,
        get_signup_status_definitions=get_signup_status_definitions,
    )


def migrate_class_user_status_from_contact_tags() -> dict[str, Any]:
    return class_user_domain_service.migrate_class_user_status_from_contact_tags(
        get_signup_status_definition_by_tag_name=get_signup_status_definition_by_tag_name,
    )


def resolve_person_identity(*, external_userid: str = "", mobile: str = "", unionid: str = "") -> dict[str, Any]:
    return identity_domain_service.resolve_person_identity(
        external_userid=external_userid,
        mobile=mobile,
        unionid=unionid,
        resolve_signup_status_for_contact=_resolve_signup_status_for_contact,
    )


def _sidebar_contact_profile(external_userid: str, owner_userid: str = "") -> dict[str, str]:
    _bind_user_ops_domain()
    return user_ops_domain_service._sidebar_contact_profile(external_userid, owner_userid)


def _resolve_binding_owner_userid(external_userid: str, owner_userid: str = "") -> str:
    _bind_user_ops_domain()
    return user_ops_domain_service._resolve_binding_owner_userid(external_userid, owner_userid)


def get_contact_binding_status(external_userid: str, owner_userid: str = "") -> dict[str, Any]:
    return identity_domain_service.get_contact_binding_status(
        external_userid,
        owner_userid,
        contact_profile_loader=_sidebar_contact_profile,
    )


def _resolve_third_party_user_id_by_mobile(mobile: str) -> str:
    return _user_ops_resolve_third_party_user_id_by_mobile_impl(mobile)


def _select_user_ops_lead_pool_member_for_sidebar(
    *,
    external_userid: str,
    mobile: str = "",
    owner_userid: str = "",
) -> dict[str, Any] | None:
    _bind_user_ops_domain()
    return user_ops_domain_service._select_user_ops_lead_pool_member_for_sidebar(
        external_userid=external_userid,
        mobile=mobile,
        owner_userid=owner_userid,
    )


def get_sidebar_lead_pool_status(*, external_userid: str, owner_userid: str = "") -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.get_sidebar_lead_pool_status(
        external_userid=external_userid,
        owner_userid=owner_userid,
    )


def upsert_sidebar_lead_pool_class_term(
    *,
    external_userid: str,
    owner_userid: str = "",
    class_term_no: int,
    operator: str = "",
) -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.upsert_sidebar_lead_pool_class_term(
        external_userid=external_userid,
        owner_userid=owner_userid,
        class_term_no=class_term_no,
        operator=operator,
    )


def _merge_lead_pool_after_mobile_bind(
    *,
    external_userid: str,
    owner_userid: str,
    mobile: str,
    operator: str = "",
) -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service._merge_lead_pool_after_mobile_bind(
        external_userid=external_userid,
        owner_userid=owner_userid,
        mobile=mobile,
        operator=operator,
    )


def bind_mobile_to_external_contact(
    *,
    external_userid: str,
    owner_userid: str,
    bind_by_userid: str,
    mobile: str,
    force_rebind: bool = False,
) -> dict[str, Any]:
    return identity_domain_service.bind_mobile_to_external_contact(
        external_userid=external_userid,
        owner_userid=owner_userid,
        bind_by_userid=bind_by_userid,
        mobile=mobile,
        force_rebind=force_rebind,
        resolve_binding_owner_userid=_resolve_binding_owner_userid,
        contact_profile_loader=_sidebar_contact_profile,
        resolve_third_party_user_id_by_mobile=_resolve_third_party_user_id_by_mobile,
        merge_lead_pool_after_mobile_bind=_merge_lead_pool_after_mobile_bind,
        conflict_error_cls=ContactBindingConflictError,
        sync_error_cls=ThirdPartyUserSyncError,
    )


def sync_user_ops_class_term_tag_definitions() -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.sync_user_ops_class_term_tag_definitions()


def reload_user_ops_pool() -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.reload_user_ops_pool()


def refresh_contact_tags_for_external_userid(
    *,
    external_userid: str,
    owner_userid: str = "",
    scoped_tag_ids: list[str] | None = None,
) -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.refresh_contact_tags_for_external_userid(
        external_userid=external_userid,
        owner_userid=owner_userid,
        scoped_tag_ids=scoped_tag_ids,
    )


def refresh_user_ops_contact_tags_for_external_userid(
    *,
    external_userid: str,
    owner_userid: str = "",
) -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.refresh_user_ops_contact_tags_for_external_userid(
        external_userid=external_userid,
        owner_userid=owner_userid,
    )


def refresh_user_ops_contact_tags_for_owner(owner_userid: str) -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.refresh_user_ops_contact_tags_for_owner(owner_userid)


def backfill_owner_class_terms_into_lead_pool(
    *,
    owner_userid: str,
    class_term_min: int = 1,
    class_term_max: int = 5,
    dry_run: bool = True,
    operator: str = "",
    entry_source: str = "",
) -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.backfill_owner_class_terms_into_lead_pool(
        owner_userid=owner_userid,
        class_term_min=class_term_min,
        class_term_max=class_term_max,
        dry_run=dry_run,
        operator=operator,
        entry_source=entry_source,
    )


def backfill_class_term_for_owner(owner_userid: str, *, operator: str = "") -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.backfill_class_term_for_owner(owner_userid, operator=operator)


def _default_owner_class_term_backfill_entry_source(owner_userid: str) -> str:
    _bind_user_ops_domain()
    return user_ops_domain_service._default_owner_class_term_backfill_entry_source(owner_userid)


def schedule_user_ops_auto_assign_class_term_job(
    *,
    external_userid: str,
    owner_userid: str,
    delay_seconds: int | None = None,
    run_after_seconds: int = 10,
    operator: str = "",
) -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.schedule_user_ops_auto_assign_class_term_job(
        external_userid=external_userid,
        owner_userid=owner_userid,
        delay_seconds=run_after_seconds if delay_seconds is None else delay_seconds,
        operator=operator,
    )


def run_due_user_ops_deferred_jobs(limit: int = 20) -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.run_due_user_ops_deferred_jobs(limit=limit)


def list_user_ops_pool(
    *,
    wecom_status: str = "",
    mobile_binding_status: str = "",
    activation_bucket: str = "",
    is_wecom_added: str = "",
    is_mobile_bound: str = "",
    huangxiaocan_activation_state: str = "",
    class_term_no: str = "",
    keyword: str = "",
    mobile: str = "",
    owner_userid: str = "",
    query: str = "",
) -> dict[str, Any]:
    return user_ops_page_service.list_user_ops_pool(
        wecom_status=wecom_status,
        mobile_binding_status=mobile_binding_status,
        activation_bucket=activation_bucket,
        is_wecom_added=is_wecom_added,
        is_mobile_bound=is_mobile_bound,
        huangxiaocan_activation_state=huangxiaocan_activation_state,
        class_term_no=class_term_no,
        keyword=keyword,
        mobile=mobile,
        owner_userid=owner_userid,
        query=query,
    )


def get_user_ops_overview(
    *,
    wecom_status: str = "",
    mobile_binding_status: str = "",
    activation_bucket: str = "",
    is_wecom_added: str = "",
    is_mobile_bound: str = "",
    huangxiaocan_activation_state: str = "",
    class_term_no: str = "",
    keyword: str = "",
    mobile: str = "",
    owner_userid: str = "",
    query: str = "",
) -> dict[str, Any]:
    return user_ops_page_service.get_user_ops_overview(
        wecom_status=wecom_status,
        mobile_binding_status=mobile_binding_status,
        activation_bucket=activation_bucket,
        is_wecom_added=is_wecom_added,
        is_mobile_bound=is_mobile_bound,
        huangxiaocan_activation_state=huangxiaocan_activation_state,
        class_term_no=class_term_no,
        keyword=keyword,
        mobile=mobile,
        owner_userid=owner_userid,
        query=query,
    )


def list_user_ops_history(limit: int = 100) -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.list_user_ops_history(limit=limit)


def export_user_ops_pool(
    *,
    wecom_status: str = "",
    mobile_binding_status: str = "",
    activation_bucket: str = "",
    is_wecom_added: str = "",
    is_mobile_bound: str = "",
    huangxiaocan_activation_state: str = "",
    class_term_no: str = "",
    keyword: str = "",
    mobile: str = "",
    owner_userid: str = "",
    query: str = "",
) -> dict[str, Any]:
    return user_ops_page_service.export_user_ops_pool(
        wecom_status=wecom_status,
        mobile_binding_status=mobile_binding_status,
        activation_bucket=activation_bucket,
        is_wecom_added=is_wecom_added,
        is_mobile_bound=is_mobile_bound,
        huangxiaocan_activation_state=huangxiaocan_activation_state,
        class_term_no=class_term_no,
        keyword=keyword,
        mobile=mobile,
        owner_userid=owner_userid,
        query=query,
    )


def set_user_ops_do_not_disturb(payload: dict[str, Any]) -> dict[str, Any]:
    return user_ops_page_service.set_user_ops_do_not_disturb(payload)


def preview_user_ops_batch_send(payload: dict[str, Any]) -> dict[str, Any]:
    return user_ops_page_service.preview_user_ops_batch_send(payload)


def execute_user_ops_batch_send(payload: dict[str, Any]) -> dict[str, Any]:
    return user_ops_page_service.execute_user_ops_batch_send(payload)


def list_user_ops_send_records(*, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    return user_ops_page_service.list_user_ops_send_records(limit=limit, offset=offset)


def get_user_ops_send_record_detail(record_id: int) -> dict[str, Any]:
    return user_ops_page_service.get_user_ops_send_record_detail(record_id)


def refresh_user_ops_send_record_status(record_id: int) -> dict[str, Any]:
    return user_ops_page_service.refresh_user_ops_send_record_status(record_id)


def write_user_ops_lead_pool_history(
    *,
    mobile: str,
    external_userid: str,
    action_type: str,
    source_type: str,
    operator: str,
    before_payload: dict[str, Any] | None,
    after_payload: dict[str, Any] | None,
    remark: str = "",
) -> None:
    _bind_user_ops_domain()
    user_ops_domain_service.write_user_ops_lead_pool_history(
        mobile=mobile,
        external_userid=external_userid,
        action_type=action_type,
        source_type=source_type,
        operator=operator,
        before_payload=before_payload,
        after_payload=after_payload,
        remark=remark,
    )


def upsert_user_ops_lead_pool_member(**kwargs: Any) -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.upsert_user_ops_lead_pool_member(**kwargs)


def upsert_user_ops_huangxiaocan_activation_source(
    *,
    mobile: str,
    activation_state: str,
    activation_remark: str = "",
    is_active: bool = True,
    created_by: str = "",
    import_batch_id: int | None = None,
) -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.upsert_user_ops_huangxiaocan_activation_source(
        mobile=mobile,
        activation_state=activation_state,
        import_batch_id=import_batch_id,
        created_by=created_by,
        is_active=is_active,
    )


def import_experience_leads(
    *,
    pasted_text: str = "",
    file_name: str = "",
    file_bytes: bytes | None = None,
    created_by: str = "",
) -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.import_experience_leads(
        pasted_text=pasted_text,
        file_name=file_name,
        file_bytes=file_bytes,
        created_by=created_by,
    )


def import_mobile_class_term_source(
    *,
    pasted_text: str = "",
    file_name: str = "",
    file_bytes: bytes | None = None,
    created_by: str = "",
) -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.import_mobile_class_term_source(
        pasted_text=pasted_text,
        file_name=file_name,
        file_bytes=file_bytes,
        created_by=created_by,
    )


def import_activation_status_source(
    *,
    pasted_text: str = "",
    file_name: str = "",
    file_bytes: bytes | None = None,
    created_by: str = "",
) -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.import_activation_status_source(
        pasted_text=pasted_text,
        file_name=file_name,
        file_bytes=file_bytes,
        created_by=created_by,
    )


def migrate_legacy_user_ops_pool_to_lead_pool(*, operator: str = "") -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service.migrate_legacy_user_ops_pool_to_lead_pool(operator=operator)


def _list_class_term_matches_for_external_contact(external_userid: str, owner_userid: str = "") -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service._list_class_term_matches_for_external_contact(external_userid, owner_userid)


def _sync_sidebar_lead_pool_class_term_tag(
    *,
    external_userid: str,
    owner_userid: str,
    class_term_no: int,
) -> dict[str, Any]:
    _bind_user_ops_domain()
    return user_ops_domain_service._sync_sidebar_lead_pool_class_term_tag(
        external_userid=external_userid,
        owner_userid=owner_userid,
        class_term_no=class_term_no,
    )


def _list_other_ownerids_with_scoped_tag_snapshots(
    external_userid: str,
    owner_userid: str,
    scoped_tag_ids: list[str],
) -> list[str]:
    return user_ops_domain_service._list_other_ownerids_with_scoped_tag_snapshots(
        external_userid,
        owner_userid,
        scoped_tag_ids,
    )


def get_messages_by_user(external_userid: str, chat_type: str | None = None) -> list[dict[str, Any]]:
    return archive_domain_service.get_messages_by_user(
        external_userid,
        chat_type,
        group_chat_map_loader=get_group_chat_map,
    )


def get_recent_messages_by_user(external_userid: str, limit: int = 20, chat_type: str | None = None) -> list[dict[str, Any]]:
    return archive_domain_service.get_recent_messages_by_user(
        external_userid,
        limit=limit,
        chat_type=chat_type,
        group_chat_map_loader=get_group_chat_map,
    )


def search_messages(external_userid: str, keyword: str) -> list[dict[str, Any]]:
    return archive_domain_service.search_messages(
        external_userid,
        keyword,
        group_chat_map_loader=get_group_chat_map,
    )


def get_message_batch(batch_id: int, *, limit: int = 200, cursor: str = "") -> dict[str, Any] | None:
    return archive_domain_service.get_message_batch(
        batch_id,
        limit=limit,
        cursor=cursor,
        group_chat_map_loader=get_group_chat_map,
    )


def resolve_questionnaire_submit_identity(
    openid: str = "",
    unionid: str = "",
    external_userid: str = "",
) -> dict[str, Any] | None:
    _bind_questionnaire_domain()
    return questionnaire_domain_service.resolve_questionnaire_submit_identity(
        openid=openid,
        unionid=unionid,
        external_userid=external_userid,
    )


def has_questionnaire_submission(questionnaire_id: int, identity: dict[str, Any] | None) -> bool:
    _bind_questionnaire_domain()
    return questionnaire_domain_service.has_questionnaire_submission(questionnaire_id, identity)


def save_questionnaire_submission(
    questionnaire: dict[str, Any],
    identity: dict[str, Any] | None,
    computed_result: dict[str, Any],
    answers: Any,
    request_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _bind_questionnaire_domain()
    return questionnaire_domain_service.save_questionnaire_submission(
        questionnaire,
        identity,
        computed_result,
        answers,
        request_meta=request_meta,
    )


def apply_questionnaire_mobile_binding(submission: dict[str, Any]) -> dict[str, Any]:
    _bind_questionnaire_domain()
    return questionnaire_domain_service.apply_questionnaire_mobile_binding(submission)


def apply_questionnaire_result_to_scrm(submission_id: int) -> dict[str, Any]:
    _bind_questionnaire_domain()
    return questionnaire_domain_service.apply_questionnaire_result_to_scrm(submission_id)


def submit_questionnaire(slug: str, payload: dict[str, Any], request_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    _bind_questionnaire_domain()
    return questionnaire_domain_service.submit_questionnaire(slug, payload, request_meta=request_meta)
