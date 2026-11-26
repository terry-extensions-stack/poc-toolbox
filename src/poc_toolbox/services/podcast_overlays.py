import base64

from io import BytesIO
from pathlib import Path

from PIL import Image

from poc_toolbox.api.podcast_contracts import CreatePodcast
from poc_toolbox.api.podcast_preview_contracts import PreviewLayout, TextRegionPreview
from poc_toolbox.services.podcast_subtitles import subtitle_timestamp
from poc_toolbox.services.podcast_typography import preview_layout


def paste_region(canvas: Image.Image, region: TextRegionPreview) -> None:
    with Image.open(BytesIO(base64.b64decode(region.image.split(',', 1)[1]))) as image:
        canvas.alpha_composite(image, region.rect[:2])


def overlay_arguments(
    directory: Path, request: CreatePodcast, duration: float, *, base_is_canvas: bool = False
) -> list[str]:
    preview = preview_layout(
        PreviewLayout(
            aspect_ratio=request.aspect_ratio,
            title=request.title,
            layout=request.layout,
            sentences=request.sentences if request.burn_subtitles else [],
        )
    )
    background = Image.new('RGBA', (preview.width, preview.height))
    paste_region(background, preview.title)
    background.save(directory / 'overlay-blank.png')
    entries = []
    subtitles = []
    cursor = 0
    pages = preview.subtitles
    for index, page in enumerate(pages):
        if page.start_time > cursor:
            entries.append(f"file 'overlay-blank.png'\nduration {(page.start_time - cursor) / 1000:.6f}\n")
        canvas = background.copy()
        if request.burn_subtitles:
            paste_region(canvas, page.region)
        filename = f'overlay-{index}.png'
        canvas.save(directory / filename)
        entries.append(f"file '{filename}'\nduration {(page.end_time - page.start_time) / 1000:.6f}\n")
        cursor = page.end_time
        text = '\n'.join(page.region.lines)
        subtitles.append(
            f'{index + 1}\n{subtitle_timestamp(page.start_time)} --> {subtitle_timestamp(page.end_time)}\n{text}\n'
        )
    if cursor < duration * 1000:
        entries.append(f"file 'overlay-blank.png'\nduration {duration - cursor / 1000:.6f}\n")
    entries.append("file 'overlay-blank.png'\n")
    (directory / 'overlays.txt').write_text(''.join(entries), encoding='utf-8')
    if request.burn_subtitles:
        (directory / 'subtitles.srt').write_text('\n'.join(subtitles), encoding='utf-8')
    x, y, _, _ = preview.video_rect
    color = request.layout.background_color.replace('#', '0x')
    base = (
        '[0:v]null[base];'
        if base_is_canvas
        else f'[0:v]pad={preview.width}:{preview.height}:{x}:{y}:color={color}[base];'
    )
    graphics_input = 1 if base_is_canvas else 2
    return [
        '-f',
        'concat',
        '-safe',
        '1',
        '-i',
        'overlays.txt',
        '-filter_complex',
        base + f'[{graphics_input}:v]fps=25,format=rgba[graphics];'
        '[base][graphics]overlay=eof_action=repeat:format=auto,format=yuv420p[out]',
    ]
