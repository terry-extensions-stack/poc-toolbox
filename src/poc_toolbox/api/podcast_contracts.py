from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from poc_toolbox.api.podcast_layout_contracts import SHARED_RENDER_VERSION, PodcastLayout

MAX_DURATION_MS = 1800000
MAX_LAYOUT_TEXT = 100000


class PodcastBatchStatusRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    ids: list[UUID] = Field(
        min_length=1,
        max_length=100,
        description='Podcast UUIDs stored in podcast_jobs.payload.id, not task or article IDs',
    )


class PodcastStatusResponse(BaseModel):
    id: UUID
    status: str | None


class PodcastBatchStatusResponse(BaseModel):
    items: list[PodcastStatusResponse]


class PodcastResponse(BaseModel):
    id: UUID
    status: str
    progress: dict
    error: str | None
    download_url: str | None
    segments_url: str
    base_video_url: str | None = None
    current_render_id: UUID | None = None
    active_render_id: UUID | None = None
    base_video_status: str | None = None


class PodcastSegmentResponse(BaseModel):
    index: int
    video_url: str
    raw_video_url: str


class PodcastSegmentPage(BaseModel):
    items: list[PodcastSegmentResponse]
    total: int
    page: int
    page_size: int


class PodcastPage(BaseModel):
    items: list[PodcastResponse]
    total: int
    page: int
    page_size: int


class Sentence(BaseModel):
    start_time: int = Field(ge=0)
    end_time: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=5000)
    words: list = Field(default_factory=list, max_length=5000)


class CreatePodcast(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    id: UUID | None = None
    article_id: UUID | None = None
    created_at: int | None = None
    updated_at: int | None = None
    title: str = Field(min_length=1, max_length=500)
    subtitle: str = Field(default='', max_length=100000)
    sentences: list[Sentence] = Field(min_length=1, max_length=500)
    audio_url: HttpUrl
    image_url: HttpUrl
    aspect_ratio: Literal['9:16', '16:9', '1:1'] = '9:16'
    burn_subtitles: bool = True
    layout: PodcastLayout | None = None

    @model_validator(mode='after')
    def validate_timeline(self) -> Self:
        if self.layout is not None:
            self.layout.validate_canvas(self.aspect_ratio)
            if (
                self.layout.render_version == SHARED_RENDER_VERSION
                and sum(len(item.text) for item in self.sentences) > MAX_LAYOUT_TEXT
            ):
                raise ValueError('Layout text exceeds the preview limit')
        previous_end = 0
        for sentence in self.sentences:
            if sentence.start_time < previous_end or sentence.end_time <= sentence.start_time:
                raise ValueError('Sentences must be ordered, non-overlapping and have positive duration')
            previous_end = sentence.end_time
        if previous_end > MAX_DURATION_MS:
            raise ValueError('Maximum podcast duration is 30 minutes')
        return self
