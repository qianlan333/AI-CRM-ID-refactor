from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ApplyQuestionnaireResultRequest(BaseModel):
    person_id: str | None = None
    external_userid: str | None = None
    mobile: str | None = None
    customer_name: str | None = None
    followup_type: str = "normal"
    questionnaire_id: int | None = None
    submission_id: str | None = None
    final_tags: list[str] = Field(default_factory=list)
    source: str = "questionnaire"
    operator: str = "system"
    reason: str = "questionnaire_submitted"


class ApplyTrialOpenedFactRequest(BaseModel):
    member_id: str
    source: str = "fixture"
    operator: str = "system"
    reason: str = "trial_opened"
    occurred_at: str | None = None


class ApplyActivationFactRequest(BaseModel):
    member_id: str | None = None
    mobile: str | None = None
    external_userid: str | None = None
    activated_at: str | None = None
    source: str = "fixture"
    operator: str = "system"
    reason: str = "activation_fact"


class OverrideFollowupTypeRequest(BaseModel):
    followup_type: str
    operator: str = "system"
    reason: str = "manual_override"


class AutomationActionRequest(BaseModel):
    operator: str = "system"
    reason: str = ""


class ActivationWebhookRequest(BaseModel):
    mobile: str | None = None
    external_userid: str | None = None
    activated_at: str | None = None
    source: str = "activation_webhook"
    operator: str = "system"


class PushOpenClawContextRequest(BaseModel):
    operator: str = "system"
    reason: str = "manual_fake_push"


class ProfileSegmentTemplateListRequest(BaseModel):
    enabled_only: bool = False
    program_id: int | None = None
    limit: int = 50
    offset: int = 0


class ProfileSegmentTemplateCreateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    segment_key: str | None = None
    code: str | None = None
    conditions: dict[str, Any] | list[Any] = Field(default_factory=dict)
    rules: dict[str, Any] | list[Any] = Field(default_factory=dict)
    status: str = "draft"
    sort_order: int = 0
    idempotency_key: str | None = None
    operator: str = "system"


class ProfileSegmentTemplateUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    segment_key: str | None = None
    code: str | None = None
    conditions: dict[str, Any] | list[Any] | None = None
    rules: dict[str, Any] | list[Any] | None = None
    status: str | None = None
    sort_order: int | None = None
    idempotency_key: str | None = None
    operator: str = "system"


class ActionTemplateListRequest(BaseModel):
    template_source: str = ""
    category: str = ""
    keyword: str = ""
    include_archived: bool = False
    limit: int = 50
    offset: int = 0


class ActionTemplateCreateRequest(BaseModel):
    name: str | None = None
    template_name: str | None = None
    code: str | None = None
    template_code: str | None = None
    template_source: str = "crm_local"
    category: str = ""
    description: str = ""
    status: str = "active"
    default_config: dict[str, Any] = Field(default_factory=dict)
    ui_schema: dict[str, Any] = Field(default_factory=dict)
    workflow_blueprint: dict[str, Any] = Field(default_factory=dict)
    node_blueprints: list[Any] = Field(default_factory=list)
    idempotency_key: str | None = None
    operator: str = "system"


class TaskGroupListRequest(BaseModel):
    program_id: int | None = None
    include_archived: bool = False
    limit: int = 50
    offset: int = 0


class TaskGroupCreateRequest(BaseModel):
    program_id: int = 0
    group_name: str | None = None
    name: str | None = None
    group_code: str | None = None
    code: str | None = None
    sort_order: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    operator: str = "system"


class ActionTemplateValidationError(ValueError):
    pass
