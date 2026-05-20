from __future__ import annotations

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
