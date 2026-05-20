from __future__ import annotations

from aicrm_next.customer_read_model.application import (
    GetCustomerChatContextQuery,
    GetCustomerDetailQuery,
    ListRecentMessagesQuery,
)
from aicrm_next.customer_read_model.dto import (
    CustomerChatContextRequest,
    CustomerDetailRequest,
    RecentMessagesRequest,
)
from aicrm_next.identity_contact.application import ResolvePersonIdentityQuery
from aicrm_next.identity_contact.dto import ResolvePersonIdentityRequest
from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.typing import JsonDict

from .fake_adapters import FakeWeComDispatchAdapter


def _looks_like_mobile(value: str) -> bool:
    return value.isdigit() and 8 <= len(value) <= 15


class McpToolDispatcher:
    def resolve_external_userid(self, arguments: JsonDict) -> str:
        external_userid = str(arguments.get("external_userid") or "").strip()
        customer_ref = str(arguments.get("customer_ref") or "").strip()
        if external_userid:
            return external_userid
        if not customer_ref:
            raise ContractError("customer_ref or external_userid is required")
        if _looks_like_mobile(customer_ref):
            identity = ResolvePersonIdentityQuery()(
                ResolvePersonIdentityRequest(mobile=customer_ref)
            )
            if not identity or not identity.external_userid:
                raise NotFoundError(f"customer not found for mobile: {customer_ref}")
            return identity.external_userid
        return customer_ref

    def dispatch(self, name: str, arguments: JsonDict) -> JsonDict:
        if name == "resolve_customer":
            return self._resolve_customer(arguments)
        if name == "get_customer_context":
            return self._get_customer_context(arguments)
        if name == "get_recent_messages":
            return self._get_recent_messages(arguments)
        raise ContractError(f"unknown MCP tool: {name}")

    def _resolve_customer(self, arguments: JsonDict) -> JsonDict:
        external_userid = self.resolve_external_userid(arguments)
        detail = GetCustomerDetailQuery()(CustomerDetailRequest(external_userid=external_userid))
        payload: JsonDict = {"external_userid": external_userid, "customer": detail["customer"]}
        if bool(arguments.get("include_context")):
            payload["context"] = self._get_customer_context(arguments)
        return payload

    def _get_customer_context(self, arguments: JsonDict) -> JsonDict:
        external_userid = self.resolve_external_userid(arguments)
        return GetCustomerChatContextQuery()(
            CustomerChatContextRequest(
                external_userid=external_userid,
                recent_message_limit=int(arguments.get("recent_message_limit") or 20),
                timeline_limit=int(arguments.get("timeline_limit") or 20),
            )
        )

    def _get_recent_messages(self, arguments: JsonDict) -> JsonDict:
        external_userid = self.resolve_external_userid(arguments)
        return ListRecentMessagesQuery()(
            RecentMessagesRequest(
                external_userid=external_userid,
                limit=int(arguments.get("limit") or arguments.get("recent_message_limit") or 20),
            )
        )


class DispatchGateway:
    def __init__(self, adapter: FakeWeComDispatchAdapter | None = None) -> None:
        self._adapter = adapter or FakeWeComDispatchAdapter()

    def dispatch_user_ops_private_message_batch(
        self,
        *,
        owner_bucket: JsonDict,
        content: str,
        images: list[dict] | None = None,
        attachments: list[dict] | None = None,
    ) -> JsonDict:
        return self._adapter.create_private_message_task(
            sender_userid=str(owner_bucket.get("sender_userid") or owner_bucket.get("owner_userid") or ""),
            external_userids=list(owner_bucket.get("external_userids") or []),
            content=content,
            images=images or [],
            attachments=attachments or [],
        )
