import json
import logging
import math
import subprocess

from pathlib import Path

from poc_toolbox.api.podcast_contracts import CreatePodcast
from poc_toolbox.services.podcast_subtitles import subtitle_filter

MAX_DURATION_SECONDS = 1800
FFMPEG_THREADS = 2
logger = logging.getLogger(__name__)


def command(arguments: list[str], directory: Path) -> str:
    if Path(arguments[0]).stem == 'ffmpeg':
        arguments = [arguments[0], '-threads', str(FFMPEG_THREADS), '-filter_threads', '1', *arguments[1:]]
    try:
        completed = subprocess.run(arguments, cwd=directory, capture_output=True, text=True, timeout=1800, check=False)
    except subprocess.TimeoutExpired:
        logger.exception('Media command timed out: executable=%s directory=%s', arguments[0], directory)
        raise RuntimeError(f'Media processing timed out ({arguments[0]})') from None
    if completed.returncode:
        diagnostic = completed.stderr[-8000:]
        logger.error(
            'Media command failed: executable=%s directory=%s exit=%s stderr=%s',
            arguments[0],
            directory,
            completed.returncode,
            diagnostic,
        )
        raise RuntimeError(f'Media processing failed ({arguments[0]}, exit={completed.returncode}): {diagnostic}')
    return completed.stdout


def audio_duration(directory: Path) -> float:
    result = command(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', 'audio'], directory)
    duration = float(json.loads(result)['format']['duration'])
    if not math.isfinite(duration) or not 0 < duration <= MAX_DURATION_SECONDS:
        raise ValueError('Audio must be between zero and 1800 seconds')
    return duration


def align_timeline(request: CreatePodcast, duration: float) -> CreatePodcast:
    audio_ms = duration * 1000
    subtitle_ms = request.sentences[-1].end_time
    if subtitle_ms <= audio_ms:
        return request
    scale = audio_ms / subtitle_ms
    sentences = [
        sentence.model_copy(
            update={
                'start_time': sentence.start_time * scale,
                'end_time': sentence.end_time * scale,
            }
        )
        for sentence in request.sentences
    ]
    return request.model_copy(update={'sentences': sentences})


def plan(request: CreatePodcast, duration: float) -> list[tuple[str, float]]:
    request = align_timeline(request, duration)
    clips = []
    for index, sentence in enumerate(request.sentences):
        start = 0 if index == 0 else sentence.start_time / 1000
        end = request.sentences[index + 1].start_time / 1000 if index + 1 < len(request.sentences) else duration
        count = math.ceil((end - start) / 12)
        clips.extend((sentence.text, (end - start) / count) for _ in range(count))
    return clips


def normalize(directory: Path, index: int, duration: float, ratio: str) -> None:
    width, height = {'9:16': (720, 1280), '16:9': (1280, 720), '1:1': (720, 720)}[ratio]
    filters = (
        f'scale={width}:{height}:force_original_aspect_ratio=decrease,'
        f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25,'
        'tpad=stop_mode=clone:stop_duration=12'
    )
    command(
        [
            'ffmpeg',
            '-v',
            'error',
            '-y',
            '-i',
            f'raw-{index}.mp4',
            '-vf',
            filters,
            '-t',
            str(duration),
            '-an',
            '-c:v',
            'libx264',
            '-threads',
            str(FFMPEG_THREADS),
            '-pix_fmt',
            'yuv420p',
            f'clip-{index}.mp4',
        ],
        directory,
    )
    command(
        [
            'ffmpeg',
            '-v',
            'error',
            '-y',
            '-sseof',
            '-0.04',
            '-i',
            f'clip-{index}.mp4',
            '-frames:v',
            '1',
            '-threads',
            str(FFMPEG_THREADS),
            '-update',
            '1',
            'frame.jpg',
        ],
        directory,
    )


def timestamp(milliseconds: int | float) -> str:
    milliseconds = round(milliseconds)
    seconds, millis = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours:02}:{minutes:02}:{seconds:02},{millis:03}'


def assemble(directory: Path, request: CreatePodcast, clips: int, duration: float) -> Path:
    request = align_timeline(request, duration)
    subtitles = []
    for index, sentence in enumerate(request.sentences, 1):
        text = (
            sentence.text.replace('<', '＜')
            .replace('>', '＞')
            .replace('{', '｛')
            .replace('}', '｝')
            .replace('\\', '＼')
        )
        text = '\n'.join(text[offset : offset + 18] for offset in range(0, len(text), 18))
        subtitles.append(f'{index}\n{timestamp(sentence.start_time)} --> {timestamp(sentence.end_time)}\n{text}\n')
    (directory / 'subtitles.srt').write_text('\n'.join(subtitles), encoding='utf-8')
    (directory / 'concat.txt').write_text(
        ''.join(f"file 'clip-{index}.mp4'\n" for index in range(clips)), encoding='utf-8'
    )
    subtitle_arguments = ['-vf', subtitle_filter(directory, request)] if request.burn_subtitles else []
    command(
        [
            'ffmpeg',
            '-v',
            'error',
            '-y',
            '-f',
            'concat',
            '-safe',
            '1',
            '-i',
            'concat.txt',
            '-i',
            'audio',
            '-map',
            '0:v:0',
            '-map',
            '1:a:0',
            *subtitle_arguments,
            '-c:v',
            'libx264',
            '-threads',
            str(FFMPEG_THREADS),
            '-pix_fmt',
            'yuv420p',
            '-c:a',
            'aac',
            '-t',
            str(duration),
            '-movflags',
            '+faststart',
            'final.mp4',
        ],
        directory,
    )
    return directory / 'final.mp4'
