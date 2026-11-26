import shutil

from pathlib import Path

from PIL import ImageFont

from poc_toolbox.api.podcast_contracts import CreatePodcast
from poc_toolbox.api.podcast_layout_contracts import VIDEO_SIZES
from poc_toolbox.config.podcast import PodcastSettings
from poc_toolbox.services.podcast_subtitles import escape_ass, subtitle_timestamp
from poc_toolbox.services.podcast_typography import wrap_text


def title_filter(directory: Path, request: CreatePodcast, duration: float) -> str:
    if request.layout is None:
        return ''
    options = request.layout.title
    text = request.title if options.text is None else options.text
    if not text.strip():
        return ''
    width, height = VIDEO_SIZES[request.aspect_ratio]
    x, y, box_width, box_height = options.rect.pixels(width, height)
    font_path = PodcastSettings().subtitle_font
    if not font_path.is_file():
        raise ValueError('PODCAST_SUBTITLE_FONT must point to an available font file')
    initial_size = max(1, round(options.font_size * height))
    minimum_size = min(initial_size, max(1, round(height * 0.012)))
    for size in range(initial_size, minimum_size - 1, -1):
        font = ImageFont.truetype(str(font_path), size)
        try:
            lines = wrap_text(text, font, max(1, box_width - 4), respect_punctuation=False)
        except ValueError:
            continue
        if len(lines) * sum(font.getmetrics()) <= box_height - 4:
            break
    else:
        raise ValueError('Title cannot fit in its region; enlarge the region or shorten the title')
    family = font.getname()[0]
    if any(character in family for character in ',\r\n'):
        raise ValueError('Title font family cannot contain commas or newlines')
    font_directory = directory / 'subtitle-fonts'
    font_directory.mkdir(exist_ok=True)
    shutil.copyfile(font_path, font_directory / f'subtitle{font_path.suffix}')
    position = rf'{{\an5\pos({x + box_width / 2},{y + box_height / 2})\clip({x},{y},{x + box_width},{y + box_height})}}'
    content = (
        f'[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\n'
        '[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BorderStyle, Outline, '
        'Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
        f'Style: Title,{family},{size},&H00FFFFFF,&H00000000,1,1,0,5,0,0,0,1\n'
        '[Events]\nFormat: Layer, Start, End, Style, Text\n'
        f'Dialogue: 0,0:00:00.00,{subtitle_timestamp(round(duration * 1000), ass=True)},Title,'
        f'{position}{escape_ass(chr(10).join(lines))}\n'
    )
    (directory / 'title.ass').write_text(content, encoding='utf-8')
    return 'subtitles=filename=title.ass:fontsdir=subtitle-fonts'
