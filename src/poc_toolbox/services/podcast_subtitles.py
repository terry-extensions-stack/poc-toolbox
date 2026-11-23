import math
import shutil
import unicodedata

from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont

from poc_toolbox.api.podcast_contracts import CreatePodcast
from poc_toolbox.config.podcast import PodcastSettings

FRAME_MS = 40
VIDEO_SIZES = {'9:16': (720, 1280), '16:9': (1280, 720), '1:1': (720, 720)}
BREAK_CHARACTERS = '，。！？；：、,.!?;: '


@dataclass(frozen=True)
class SubtitleLayout:
    width: int
    height: int
    left: int
    top: int
    right: int
    bottom: int
    font_size: int
    padding: int


def layout_for(ratio: str) -> SubtitleLayout:
    width, height = VIDEO_SIZES[ratio]
    return SubtitleLayout(
        width,
        height,
        math.ceil(width * 0.08 / 2) * 2,
        math.ceil(height * 0.86 / 2) * 2,
        math.floor(width * 0.92 / 2) * 2,
        math.floor(height * 0.94 / 2) * 2,
        max(1, round(height * 0.024)),
        max(2, round(height * 0.005)),
    )


def wrap_lines(text: str, font: ImageFont.FreeTypeFont, maximum_width: float) -> list[str]:
    remaining = text.replace('\r\n', '\n').replace('\r', '\n').replace('\t', ' ')
    lines = []
    while remaining:
        end = 0
        while end < len(remaining) and remaining[end] != '\n' and font.getlength(remaining[: end + 1]) <= maximum_width:
            end += 1
        if end == 0 and remaining[0] != '\n':
            raise ValueError('Subtitle character exceeds available width')
        if end < len(remaining) and remaining[end] != '\n':
            boundary = max((index + 1 for index in range(end) if remaining[index] in BREAK_CHARACTERS), default=0)
            end = boundary or end
        lines.append(remaining[:end])
        remaining = remaining[end + 1 :] if remaining[end : end + 1] == '\n' else remaining[end:]
    return lines or ['']


def text_weight(text: str) -> int:
    return sum(not character.isspace() and not unicodedata.category(character).startswith('P') for character in text)


def subtitle_cues(
    request: CreatePodcast, font: ImageFont.FreeTypeFont, layout: SubtitleLayout
) -> list[tuple[int, int, str]]:
    cues = []
    available_width = (layout.right - layout.left - 2 * layout.padding) * 0.9
    for sentence in request.sentences:
        lines = wrap_lines(sentence.text, font, available_width)
        pages = ['\n'.join(lines[index : index + 2]) for index in range(0, len(lines), 2)]
        start, end = round(sentence.start_time), round(sentence.end_time)
        weights = [text_weight(page) for page in pages]
        weights = weights if all(weights) else [max(1, len(page)) for page in pages]
        total = sum(weights)
        elapsed = 0
        for page, weight in zip(pages, weights, strict=True):
            page_start = start + round((end - start) * elapsed / total)
            elapsed += weight
            page_end = start + round((end - start) * elapsed / total)
            if page_end - page_start < FRAME_MS:
                raise ValueError('Subtitle page duration is shorter than one video frame')
            cues.append((page_start, page_end, page))
    return cues


def subtitle_timestamp(milliseconds: int, *, ass: bool = False) -> str:
    seconds, millis = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if ass:
        return f'{hours}:{minutes:02}:{seconds:02}.{millis // 10:02}'
    return f'{hours:02}:{minutes:02}:{seconds:02},{millis:03}'


def escape_ass(text: str) -> str:
    return text.replace('\\', '＼').replace('{', '｛').replace('}', '｝').replace('\n', r'\N')


def write_subtitles(directory: Path, request: CreatePodcast) -> SubtitleLayout:
    layout = layout_for(request.aspect_ratio)
    font_path = PodcastSettings().subtitle_font
    if not font_path.is_file():
        raise ValueError('PODCAST_SUBTITLE_FONT must point to an available font file')
    font = ImageFont.truetype(str(font_path), layout.font_size)
    font_directory = directory / 'subtitle-fonts'
    font_directory.mkdir(exist_ok=True)
    shutil.copyfile(font_path, font_directory / f'subtitle{font_path.suffix}')
    cues = subtitle_cues(request, font, layout)
    family = font.getname()[0]
    if any(character in family for character in ',\r\n'):
        raise ValueError('Subtitle font family cannot contain commas or newlines')
    header = (
        f'[Script Info]\nScriptType: v4.00+\nPlayResX: {layout.width}\nPlayResY: {layout.height}\nWrapStyle: 2\n'
        '[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BorderStyle, Outline, '
        'Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
        f'Style: Default,{family},{layout.font_size},&H00FFFFFF,&H00000000,1,1,0,5,0,0,0,1\n'
        '[Events]\nFormat: Layer, Start, End, Style, Text\n'
    )
    position = (
        rf'{{\an5\pos({(layout.left + layout.right) / 2},{(layout.top + layout.bottom) / 2})'
        rf'\clip({layout.left},{layout.top},{layout.right},{layout.bottom})}}'
    )
    events = [
        f'Dialogue: 0,{subtitle_timestamp(start, ass=True)},{subtitle_timestamp(end, ass=True)},Default,'
        f'{position}{escape_ass(text)}\n'
        for start, end, text in cues
    ]
    (directory / 'subtitles.ass').write_text(header + ''.join(events), encoding='utf-8')
    srt = [
        f'{index}\n{subtitle_timestamp(start)} --> {subtitle_timestamp(end)}\n{text}\n'
        for index, (start, end, text) in enumerate(cues, 1)
    ]
    (directory / 'subtitles.srt').write_text('\n'.join(srt), encoding='utf-8')
    return layout


def subtitle_filter(directory: Path, request: CreatePodcast) -> str:
    layout = write_subtitles(directory, request)
    return (
        f'drawbox=x={layout.left}:y={layout.top}:w={layout.right - layout.left}:'
        f'h={layout.bottom - layout.top}:color=black@0.45:t=fill,'
        'subtitles=filename=subtitles.ass:fontsdir=subtitle-fonts'
    )
