from __future__ import annotations

LEGACY_COMPATIBILITY_SHIM = True

from legacy_flask.routes import (  # noqa: F401
    ArchiveAdapterClient,
    _contact_client,
    _contact_sync_retry_limit,
    _default_owner_userid,
    _dispatch_background_task,
    _handle_group_chat_change,
    _process_external_contact_event,
    _run_user_ops_deferred_jobs_after_delay,
    _trigger_incremental_archive_sync,
    bp,
    list_available_wecom_tags,
)

__all__ = [
    "ArchiveAdapterClient",
    "LEGACY_COMPATIBILITY_SHIM",
    "_contact_client",
    "_contact_sync_retry_limit",
    "_default_owner_userid",
    "_dispatch_background_task",
    "_handle_group_chat_change",
    "_process_external_contact_event",
    "_run_user_ops_deferred_jobs_after_delay",
    "_trigger_incremental_archive_sync",
    "bp",
    "list_available_wecom_tags",
]
