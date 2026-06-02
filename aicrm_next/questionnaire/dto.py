from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QuestionnaireOptionInput(BaseModel):
    id: str | int | None = None
    label: str = ""
    value: str = ""
    tag_codes: list[str] = Field(default_factory=list)
    score: int = 0


class QuestionnaireQuestionInput(BaseModel):
    id: str | int | None = None
    type: str = "single_choice"
    title: str
    required: bool = False
    sidebar_profile_field: str = ""
    options: list[QuestionnaireOptionInput] = Field(default_factory=list)


class QuestionnaireUpsertRequest(BaseModel):
    slug: str | None = None
    title: str
    description: str = ""
    enabled: bool = True
    redirect_url: str = ""
    submit_button_text: str = "提交"
    questions: list[QuestionnaireQuestionInput] = Field(default_factory=list)
    external_push_config: dict[str, Any] = Field(default_factory=dict)


class QuestionnaireSubmitRequest(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)
    respondent_identity: dict[str, Any] = Field(default_factory=dict)


class OAuthStartRequest(BaseModel):
    slug: str | None = None
    state: str | None = None
    redirect: str | None = None
    scene: str | None = None
    openid: str | None = None
    unionid: str | None = None
    external_userid: str | None = None


class OAuthCallbackRequest(BaseModel):
    code: str | None = None
    state: str | None = None
    redirect: str | None = None
    error: str | None = None
    errcode: str | None = None
    openid: str | None = None
    unionid: str | None = None
    external_userid: str | None = None
