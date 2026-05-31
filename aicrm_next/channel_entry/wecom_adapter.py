from __future__ import annotations

from typing import Any

from .domain import text


class WeComAdapterBlocked(RuntimeError):
    pass


class GuardedWeComAdapter:
    """Adapter boundary for WeCom side effects.

    Real calls are intentionally not enabled here. Tests and staging wiring can
    inject an object with the same methods.
    """

    def send_welcome_msg(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise WeComAdapterBlocked("wecom_welcome_external_call_blocked")

    def mark_external_contact_tags(
        self,
        *,
        external_userid: str,
        follow_user_userid: str,
        add_tags: list[str],
        remove_tags: list[str],
    ) -> dict[str, Any]:
        raise WeComAdapterBlocked("wecom_tag_external_call_blocked")

    def get_external_contact_detail(self, external_userid: str) -> dict[str, Any]:
        raise WeComAdapterBlocked(f"wecom_contact_detail_external_call_blocked:{text(external_userid)}")


_adapter: Any = GuardedWeComAdapter()


def set_wecom_adapter(adapter: Any) -> None:
    global _adapter
    _adapter = adapter


def get_wecom_adapter() -> Any:
    return _adapter

