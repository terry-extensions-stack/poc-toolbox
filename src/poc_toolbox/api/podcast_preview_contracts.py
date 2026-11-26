from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from poc_toolbox.api.podcast_contracts import MAX_DURATION_MS, MAX_LAYOUT_TEXT, Sentence
from poc_toolbox.api.podcast_layout_contracts import SHARED_RENDER_VERSION, PodcastLayout


class PreviewLayout(BaseModel):
    model_config = ConfigDict(extra='forbid')
    aspect_ratio: Literal['9:16', '16:9', '1:1'] = '9:16'
    title: str = Field(default='', max_length=500)
    layout: PodcastLayout
    sentences: list[Sentence] = Field(default_factory=list, max_length=500)

    @model_validator(mode='after')
    def validate_layout(self) -> Self:
        self.layout.validate_canvas(self.aspect_ratio)
        if self.layout.render_version != SHARED_RENDER_VERSION:
            raise ValueError('Layout preview requires render_version=2')
        previous_end = 0
        for sentence in self.sentences:
            if sentence.start_time < previous_end or sentence.end_time <= sentence.start_time:
                raise ValueError('Sentences must be ordered and non-overlapping')
            previous_end = sentence.end_time
        if previous_end > MAX_DURATION_MS or sum(len(item.text) for item in self.sentences) > MAX_LAYOUT_TEXT:
            raise ValueError('Preview exceeds the podcast text or duration limit')
        return self


class TextRegionPreview(BaseModel):
    rect: tuple[int, int, int, int]
    font_size: int
    line_height: int
    lines: list[str]
    image: str


class SubtitlePagePreview(BaseModel):
    start_time: int
    end_time: int
    region: TextRegionPreview


class LayoutPreview(BaseModel):
    width: int
    height: int
    video_rect: tuple[int, int, int, int]
    title: TextRegionPreview
    subtitles: list[SubtitlePagePreview]
