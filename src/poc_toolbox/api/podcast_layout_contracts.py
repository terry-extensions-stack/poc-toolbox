from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

VIDEO_SIZES = {'9:16': (720, 1280), '16:9': (1280, 720), '1:1': (720, 720)}
MIN_REGION_PIXELS = 2
SHARED_RENDER_VERSION = 2
SourceRatio = Literal['16:9', '4:3', '1:1', '3:4', '9:16', '21:9', 'adaptive']


class LayoutModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class LayoutRect(LayoutModel):
    x: float = Field(default=0, ge=0, le=1)
    y: float = Field(default=0, ge=0, le=1)
    width: float = Field(default=1, gt=0, le=1)
    height: float = Field(default=1, gt=0, le=1)

    @model_validator(mode='after')
    def validate_bounds(self) -> Self:
        if self.x + self.width > 1 + 1e-9 or self.y + self.height > 1 + 1e-9:
            raise ValueError('Layout rectangle must stay inside the canvas')
        return self

    def pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        left, top = round(self.x * width), round(self.y * height)
        right = min(width, round((self.x + self.width) * width))
        bottom = min(height, round((self.y + self.height) * height))
        return left, top, right - left, bottom - top


class TitleLayout(LayoutModel):
    text: str | None = Field(default=None, max_length=500)
    rect: LayoutRect = Field(default_factory=lambda: LayoutRect(x=0.08, y=0.12, width=0.84, height=0.16))
    font_size: float = Field(default=0.04, gt=0, le=1)


class VideoLayout(LayoutModel):
    rect: LayoutRect = Field(default_factory=lambda: LayoutRect(x=0, y=0.341796875, width=1, height=0.31640625))
    fit: Literal['contain', 'cover'] = 'contain'


class SubtitleOptions(LayoutModel):
    rect: LayoutRect = Field(default_factory=lambda: LayoutRect(x=0.08, y=0.72, width=0.84, height=0.16))
    font_size: float = Field(default=0.024, gt=0, le=1)


class PodcastLayout(LayoutModel):
    render_version: Literal[1, 2] = 1
    preset: Literal['podcast'] = 'podcast'
    source_ratio: SourceRatio = '16:9'
    background_color: str = Field(default='#000000', pattern=r'^#[0-9a-fA-F]{6}$')
    title: TitleLayout = Field(default_factory=TitleLayout)
    video: VideoLayout = Field(default_factory=VideoLayout)
    subtitles: SubtitleOptions = Field(default_factory=SubtitleOptions)

    @model_validator(mode='before')
    @classmethod
    def merge_regions(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        result = dict(value)
        for name, model in (('title', TitleLayout), ('video', VideoLayout), ('subtitles', SubtitleOptions)):
            region = result.get(name)
            if isinstance(region, dict) and isinstance(region.get('rect'), dict):
                result[name] = {**region, 'rect': {**model().rect.model_dump(), **region['rect']}}
        return result

    def video_pixels(self, ratio: str) -> tuple[int, int, int, int]:
        x, y, width, height = self.video.rect.pixels(*VIDEO_SIZES[ratio])
        return x // 2 * 2, y // 2 * 2, width // 2 * 2, height // 2 * 2

    def validate_canvas(self, ratio: str) -> None:
        width, height = VIDEO_SIZES[ratio]
        for rect in (self.title.rect, self.video.rect, self.subtitles.rect):
            _, _, box_width, box_height = rect.pixels(width, height)
            if min(box_width, box_height) < MIN_REGION_PIXELS:
                raise ValueError('Layout regions must occupy at least two pixels in each dimension')
