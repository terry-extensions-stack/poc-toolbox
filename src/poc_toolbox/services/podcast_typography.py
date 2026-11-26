import base64
import math

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from poc_toolbox.api.podcast_layout_contracts import VIDEO_SIZES
from poc_toolbox.api.podcast_preview_contracts import (
    LayoutPreview,
    PreviewLayout,
    SubtitlePagePreview,
    TextRegionPreview,
)
from poc_toolbox.config.podcast import PodcastSettings
from poc_toolbox.services.podcast_subtitles import FRAME_MS, text_weight

NO_LINE_START = '，。！？；：、,.!?;:）》】」』”’'
NO_LINE_END = '（《【「『“‘'


def wrap_text(text: str, font: ImageFont.FreeTypeFont, width: int, *, respect_punctuation: bool = True) -> list[str]:
    lines = []
    for paragraph in text.replace('\r\n', '\n').replace('\r', '\n').replace('\t', ' ').split('\n'):
        remaining = paragraph
        while remaining:
            end = 0
            while end < len(remaining) and font.getlength(remaining[: end + 1]) <= width:
                end += 1
            if not end:
                raise ValueError('Text character exceeds available width')
            if respect_punctuation and end < len(remaining):
                while end > 1 and (remaining[end] in NO_LINE_START or remaining[end - 1] in NO_LINE_END):
                    end -= 1
            lines.append(remaining[:end])
            remaining = remaining[end:]
        if not paragraph:
            lines.append('')
    return lines


def region_image(region: TextRegionPreview, font: ImageFont.FreeTypeFont, *, title: bool) -> Image.Image:
    _, _, width, height = region.rect
    background = (0, 0, 0, 0) if title else (0, 0, 0, 115)
    image = Image.new('RGBA', (width, height), background)
    draw = ImageDraw.Draw(image)
    top = (height - len(region.lines) * region.line_height) / 2
    for index, line in enumerate(region.lines):
        bounds = font.getbbox(line)
        y = top + index * region.line_height + (region.line_height - (bounds[3] - bounds[1])) / 2
        draw.text(
            (width / 2, y),
            line,
            font=font,
            anchor='mt',
            fill='white',
            stroke_width=1 if title else 0,
            stroke_fill='white',
        )
    return image


def encode_region(region: TextRegionPreview, font: ImageFont.FreeTypeFont, *, title: bool) -> TextRegionPreview:
    buffer = BytesIO()
    region_image(region, font, title=title).save(buffer, format='PNG')
    return region.model_copy(update={'image': 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()})


def title_region(request: PreviewLayout, font_path: str) -> TextRegionPreview:
    width, height = VIDEO_SIZES[request.aspect_ratio]
    options = request.layout.title
    rect = options.rect.pixels(width, height)
    text = request.title if options.text is None else options.text
    initial_size = max(1, round(options.font_size * height))
    if not text.strip():
        font = ImageFont.truetype(font_path, initial_size)
        region = TextRegionPreview(
            rect=rect,
            font_size=initial_size,
            line_height=math.ceil(initial_size * 1.25),
            lines=[],
            image='',
        )
        return encode_region(region, font, title=True)
    minimum_size = min(initial_size, max(1, round(height * 0.012)))
    for size in range(initial_size, minimum_size - 1, -1):
        font = ImageFont.truetype(font_path, size)
        try:
            lines = wrap_text(text, font, max(1, rect[2] - 4), respect_punctuation=False)
        except ValueError:
            continue
        line_height = math.ceil(size * 1.25)
        if len(lines) * line_height <= rect[3] - 4:
            region = TextRegionPreview(
                rect=rect,
                font_size=size,
                line_height=line_height,
                lines=lines,
                image='',
            )
            return encode_region(region, font, title=True)
    raise ValueError('Title cannot fit in its region; enlarge the region or shorten the title')


def subtitle_pages(request: PreviewLayout, font_path: str) -> list[SubtitlePagePreview]:
    width, height = VIDEO_SIZES[request.aspect_ratio]
    options = request.layout.subtitles
    rect = options.rect.pixels(width, height)
    size = max(1, round(options.font_size * height))
    font = ImageFont.truetype(font_path, size)
    line_height = math.ceil(size * 1.25)
    padding = max(2, round(height * 0.005))
    if 2 * line_height + 2 * padding > rect[3]:
        raise ValueError('Subtitle region is too short for two lines at the configured font size')
    cues = []
    for sentence in request.sentences:
        lines = wrap_text(sentence.text, font, max(1, rect[2] - 2 * padding))
        pages = [lines[index : index + 2] for index in range(0, len(lines), 2)]
        weights = [max(1, text_weight(''.join(page))) for page in pages]
        total, elapsed = sum(weights), 0
        duration = sentence.end_time - sentence.start_time
        for page, weight in zip(pages, weights, strict=True):
            start = sentence.start_time + round(duration * elapsed / total)
            elapsed += weight
            end = sentence.start_time + round(duration * elapsed / total)
            if end - start < FRAME_MS:
                raise ValueError('Subtitle page duration is shorter than one video frame')
            region = TextRegionPreview(rect=rect, font_size=size, line_height=line_height, lines=page, image='')
            cues.append(
                SubtitlePagePreview(
                    start_time=start,
                    end_time=end,
                    region=encode_region(region, font, title=False),
                )
            )
    return cues


def preview_layout(request: PreviewLayout) -> LayoutPreview:
    font_path = PodcastSettings().layout_font
    if not font_path.is_file():
        raise FileNotFoundError('PODCAST_LAYOUT_FONT must point to the shared layout font')
    width, height = VIDEO_SIZES[request.aspect_ratio]
    return LayoutPreview(
        width=width,
        height=height,
        video_rect=request.layout.video_pixels(request.aspect_ratio),
        title=title_region(request, str(font_path)),
        subtitles=subtitle_pages(request, str(font_path)),
    )
