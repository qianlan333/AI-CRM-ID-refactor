from __future__ import annotations

from .questionnaire_shared import (
    _json_array,
    _json_dumps,
    _normalize_bool,
    _normalize_float,
    _normalize_int,
    _normalize_required_integer,
    _questionnaire_exists_by_slug,
    _slugify_questionnaire,
    _validate_tag_codes_payload,
)
from .questionnaire_admin_service import (
    _get_questionnaire_row,
    _normalize_questionnaire_payload,
    _questionnaire_submission_stats,
    create_questionnaire,
    delete_questionnaire,
    disable_questionnaire,
    export_questionnaire_submissions,
    get_latest_questionnaire_submit_debug,
    get_public_questionnaire_by_slug,
    get_questionnaire_detail,
    list_available_wecom_tags,
    list_questionnaires,
    update_questionnaire,
)
from .questionnaire_submit_service import (
    _build_respondent_key,
    apply_questionnaire_mobile_binding,
    apply_questionnaire_result_to_scrm,
    compute_questionnaire_result,
    has_questionnaire_submission,
    resolve_questionnaire_submit_identity,
    save_questionnaire_submission,
    submit_questionnaire,
    validate_questionnaire_answers,
)
