from __future__ import annotations

from typing import Any

from ..db import get_db


SENSITIVE_KEYS = {
    "WECOM_CONTACT_SECRET",
    "WECOM_SECRET",
    "WECOM_ARCHIVE_SECRET",
    "WECOM_CALLBACK_TOKEN",
    "WECOM_CALLBACK_AES_KEY",
    "WECHAT_MP_APP_SECRET",
}


def mask_value(key: str, value: str) -> str:
    if key not in SENSITIVE_KEYS:
        return value
    if not value:
        return ""
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}***{value[-2:]}"


def get_setting(key: str) -> str | None:
    row = get_db().execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_settings(settings: dict[str, Any]) -> None:
    db = get_db()
    for key, value in settings.items():
        db.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, str(value)),
        )
    db.commit()


def list_settings_snapshot(config: dict[str, Any]) -> dict[str, str]:
    keys = [
        "WECOM_CORP_ID",
        "WECOM_SECRET",
        "WECOM_CONTACT_SECRET",
        "WECOM_AGENT_ID",
        "WECOM_API_BASE",
        "WECOM_ARCHIVE_SECRET",
        "WECOM_PRIVATE_KEY_PATH",
        "WECOM_SDK_LIB_PATH",
        "WECOM_DEFAULT_OWNER_USERID",
        "WECOM_CALLBACK_TOKEN",
        "WECOM_CALLBACK_AES_KEY",
        "WECOM_ARCHIVE_TIMEOUT",
        "WECHAT_MP_APP_ID",
        "WECHAT_MP_APP_SECRET",
        "WECHAT_MP_OAUTH_SCOPE",
    ]
    snapshot: dict[str, str] = {}
    for key in keys:
        value = get_setting(key)
        if value is None:
            value = str(config.get(key, ""))
        snapshot[key] = mask_value(key, value)
    return snapshot
