from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from poc_toolbox.api.podcast_contracts import MAX_LAYOUT_TEXT, Sentence
from poc_toolbox.api.podcast_layout_contracts import LayoutRect, PodcastLayout


class EditRegion(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    rect: LayoutRect
    font_size: float = Field(gt=0, le=1)


class EditTitle(EditRegion):
    text: str = Field(max_length=500)


class CreateRender(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    title: EditTitle
    subtitles: EditRegion
    subtitle_texts: list[Annotated[str, Field(min_length=1, max_length=5000)]] | None = Field(
        default=None, max_length=500
    )
    burn_subtitles: bool = True

    @model_validator(mode='after')
    def validate_text_limit(self) -> Self:
        if self.subtitle_texts is not None and sum(map(len, self.subtitle_texts)) > MAX_LAYOUT_TEXT:
            raise ValueError('Subtitle text exceeds the layout limit')
        return self


class EditSegment(BaseModel):
    index: int
    start_time: int
    end_time: int
    video_url: str


class EditConfig(BaseModel):
    can_edit: bool
    unavailable_reason: str | None = None
    aspect_ratio: Literal['9:16', '16:9', '1:1']
    duration_ms: int | None = None
    layout: PodcastLayout
    sentences: list[Sentence]
    burn_subtitles: bool
    segments: list[EditSegment] = Field(default_factory=list)
    base_video_url: str | None = None
    current_render_id: UUID | None = None
    active_render_id: UUID | None = None
    active_edit: CreateRender | None = None
    download_url: str | None = None


class RenderResponse(BaseModel):
    id: UUID
    source_job_id: UUID
    status: str
    progress: dict
    error: str | None
    download_url: str | None
    edit: CreateRender
    is_current: bool = False


class RenderPage(BaseModel):
    items: list[RenderResponse]
    total: int
    page: int
    page_size: int
