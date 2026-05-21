from __future__ import annotations

from flask import Response

from wecom_ability_service.archive_adapter import ArchiveAdapterClient
from wecom_ability_service.services import list_available_wecom_tags
from legacy_flask.http import bp
from wecom_ability_service.http.background_jobs import (
    _dispatch_background_task,
    _handle_group_chat_change,
    _process_external_contact_event,
    _run_user_ops_deferred_jobs_after_delay,
)
from wecom_ability_service.http.common import _contact_client, _contact_sync_retry_limit, _default_owner_userid
from wecom_ability_service.http.sync_jobs import _trigger_incremental_archive_sync


def favicon() -> Response:
    return Response(status=204)


favicon.__module__ = "wecom_ability_service"
