from __future__ import annotations

import os
import urllib.request

from scripts import internal_http
from scripts.script_runtime import (
    emit_json,
    ensure_repo_root_on_path,
    read_app_host,
    read_app_port,
    read_int_env,
    read_internal_access_token,
    read_internal_api_base_url,
    read_internal_tls_context,
)


DEFAULT_PATH = "/api/archive/sync"


def run() -> str:
    if os.getenv("WECOM_ARCHIVE_SYNC_MODE", "direct").strip().lower() == "http":
        return run_http()
    return run_direct()


def _payload() -> dict[str, object]:
    owner_userid = os.getenv("WECOM_DEFAULT_OWNER_USERID", "")
    return {
        "start_time": os.getenv("WECOM_ARCHIVE_SYNC_START_TIME", "2000-01-01 00:00:00"),
        "end_time": os.getenv("WECOM_ARCHIVE_SYNC_END_TIME", "2099-12-31 23:59:59"),
        "owner_userid": owner_userid,
        "cursor": os.getenv("WECOM_ARCHIVE_SYNC_CURSOR", ""),
        "limit": read_int_env("WECOM_ARCHIVE_SYNC_LIMIT", 100),
        "max_pages": read_int_env("WECOM_ARCHIVE_SYNC_MAX_PAGES", 1000),
    }


def run_direct() -> str:
    ensure_repo_root_on_path()
    from aicrm_next.message_archive.repo import PostgresArchiveSyncRepository
    from aicrm_next.message_archive.sync_service import execute_archive_sync

    payload = _payload()
    response_payload = execute_archive_sync(
        start_time=str(payload["start_time"]),
        end_time=str(payload["end_time"]),
        owner_userid=str(payload["owner_userid"]),
        cursor=str(payload["cursor"]),
        limit=int(payload["limit"]),
        max_pages=int(payload["max_pages"]),
        repo=PostgresArchiveSyncRepository(source_change_recorder=_record_archive_source_change),
    )
    return emit_json(response_payload)


def _record_archive_source_change(conn, inserted_count: int, last_seq: int) -> dict[str, object]:
    """Composition-root adapter for one PII-free transactional source event."""

    from aicrm_next.platform_foundation.command_bus.models import CommandContext
    from aicrm_next.platform_foundation.internal_events.models import InternalEventCreateRequest
    from aicrm_next.platform_foundation.internal_events.outbox import enqueue_transactional_internal_event_outbox

    return enqueue_transactional_internal_event_outbox(
        conn,
        InternalEventCreateRequest(
            event_type="message_archive.batch_ingested",
            aggregate_type="message_archive_sync",
            aggregate_id=str(int(last_seq)),
            payload={"inserted_count": int(inserted_count), "last_seq": int(last_seq)},
            payload_summary={"inserted_count": int(inserted_count), "last_seq": int(last_seq)},
            context=CommandContext(
                actor_id="archive_sync",
                actor_type="system",
                source_route="scripts.run_incremental_archive_sync",
            ),
            idempotency_key=f"message_archive.batch_ingested:{int(last_seq)}",
            source_module="message_archive.repo",
            source_command_id=f"archive_sync:{int(last_seq)}",
            execution_id=f"exe_archive_sync_{int(last_seq)}",
        ),
    )


def run_http() -> str:
    host = read_app_host()
    port = read_app_port()
    token = read_internal_access_token(purpose="archive", scopes=("write",))
    response_payload = internal_http.post_json(
        host=host,
        port=port,
        token=token,
        base_url=read_internal_api_base_url(),
        ssl_context=read_internal_tls_context(),
        path=DEFAULT_PATH,
        payload=_payload(),
        timeout_seconds=read_int_env("WECOM_ARCHIVE_SYNC_TIMEOUT_SECONDS", 600),
        urlopen=urllib.request.urlopen,
    )
    return emit_json(response_payload)


def main() -> None:
    run()


if __name__ == "__main__":
    main()
