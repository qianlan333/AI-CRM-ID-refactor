from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GroupOpsPlanListRequest(BaseModel):
    keyword: str = ""
    plan_type: str = ""
    status: str = ""
    limit: int = 50
    offset: int = 0


class GroupOpsPlanCreateRequest(BaseModel):
    plan_code: str | None = None
    plan_name: str | None = None
    plan_type: str = "standard"
    owner_userid: str | None = None
    status: str = "draft"
    operator: str = "system"


class GroupOpsPlanUpdateRequest(BaseModel):
    plan_code: str | None = None
    plan_name: str | None = None
    plan_type: str | None = None
    owner_userid: str | None = None
    status: str | None = None
    operator: str = "system"


class GroupOpsBindGroupRequest(BaseModel):
    chat_id: str
    operator: str = "system"


class GroupOpsNodeRequest(BaseModel):
    day_index: int = 1
    trigger_time_label: str = ""
    action_title: str = ""
    text_content: str = ""
    attachments: list[Any] = Field(default_factory=list)
    sort_order: int = 0
    status: str = "active"
    operator: str = "system"


class GroupOpsGroupsRequest(BaseModel):
    keyword: str = ""
    owner_userid: str = ""
    plan_id: int | None = None
    bind_status: str = ""
    limit: int = 50
    offset: int = 0


class GroupOpsWebhookReceiveRequest(BaseModel):
    idempotency_key: str
    send_mode: str = "queued"
    scheduled_at: str | None = None
    content: dict[str, Any] = Field(default_factory=dict)
