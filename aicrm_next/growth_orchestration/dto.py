from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GrowthProgram(BaseModel):
    program_key: str
    program_type: str
    title: str = ""
    status: str = ""
    owner_userid: str = ""
    member_count: int = 0
    active_member_count: int = 0
    task_count: int = 0
    last_activity_at: datetime | None = None
    source_table: str
    source_id: str


class GrowthProgramList(BaseModel):
    ok: bool = True
    items: list[GrowthProgram] = Field(default_factory=list)
    limit: int = 50
    offset: int = 0
