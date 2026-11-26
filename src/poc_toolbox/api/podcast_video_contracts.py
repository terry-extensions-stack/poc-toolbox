from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ArticleSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    title: str | None
    link: str | None
    cover: str | None
    publish_at: int | None
    is_copyright: bool | None
    feedname: str | None = Field(validation_alias='feed_name')
    feedcover: str | None = Field(validation_alias='feed_cover')


class PodcastVideoResponse(BaseModel):
    id: UUID
    job_id: UUID
    article_id: UUID | None
    title: str
    image_url: str | None = None
    status: Literal['SUCCEEDED']
    created_at: datetime | None
    download_url: str
    article: ArticleSummary | None


class PodcastVideoPage(BaseModel):
    items: list[PodcastVideoResponse]
    total: int
    page: int
    page_size: int
