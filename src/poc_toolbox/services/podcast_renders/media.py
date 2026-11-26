from pathlib import Path

from poc_toolbox.api.podcast_contracts import CreatePodcast
from poc_toolbox.services.podcast_media import FFMPEG_THREADS, command
from poc_toolbox.services.podcast_overlays import overlay_arguments


def render_base(directory: Path, request: CreatePodcast, duration: float) -> Path:
    overlays = overlay_arguments(directory, request, duration, base_is_canvas=True)
    command(
        [
            'ffmpeg',
            '-v',
            'error',
            '-y',
            '-i',
            'base.mp4',
            *overlays,
            '-map',
            '[out]',
            '-map',
            '0:a:0',
            '-c:v',
            'libx264',
            '-threads',
            str(FFMPEG_THREADS),
            '-pix_fmt',
            'yuv420p',
            '-c:a',
            'copy',
            '-t',
            str(duration),
            '-movflags',
            '+faststart',
            'final.mp4',
        ],
        directory,
    )
    return directory / 'final.mp4'
