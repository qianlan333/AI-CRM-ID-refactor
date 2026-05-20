from __future__ import annotations

from pydantic import BaseModel, Field


class ImageUpsertRequest(BaseModel):
    name: str = Field(min_length=1)
    file_name: str = "fixture.png"
    content_type: str = "image/png"
    file_size: int = 0
    width: int = 1
    height: int = 1
    data_url: str = "data:image/png;base64,ZmFrZQ=="
    tags: list[str] = Field(default_factory=list)


class ImageFromUrlRequest(BaseModel):
    url: str
    name: str | None = None
    tags: list[str] = Field(default_factory=list)


class ImageFromBase64Request(BaseModel):
    data_base64: str
    name: str | None = None
    file_name: str = "base64.png"
    tags: list[str] = Field(default_factory=list)


class AttachmentUpsertRequest(BaseModel):
    name: str = Field(min_length=1)
    file_name: str
    mime_type: str = "application/octet-stream"
    file_size: int = 0
    data_base64: str = ""
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True


class MiniprogramUpsertRequest(BaseModel):
    title: str = Field(min_length=1)
    appid: str
    page_path: str
    thumb_image_id: str | None = None
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
