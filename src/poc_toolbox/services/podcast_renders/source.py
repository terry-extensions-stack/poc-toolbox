import asyncio

from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select

from poc_toolbox.api.errors import APIError
from poc_toolbox.api.podcast_contracts import CreatePodcast, Sentence
from poc_toolbox.api.podcast_layout_contracts import PodcastLayout, VideoLayout
from poc_toolbox.api.podcast_preview_contracts import PreviewLayout
from poc_toolbox.api.podcast_render_contracts import CreateRender, EditConfig, EditSegment
from poc_toolbox.config.podcast import PodcastSettings
from poc_toolbox.db_models.podcast import PodcastJob
from poc_toolbox.db_models.podcast_render import PodcastRender
from poc_toolbox.services import podcast_media as media
from poc_toolbox.services.podcast_typography import preview_layout


def source_directory(job_id) -> Path:
    return PodcastSettings().work_dir / str(job_id)


def source_request(job: PodcastJob) -> CreatePodcast:
    request = CreatePodcast.model_validate({'burn_subtitles': False, **job.payload})
    if request.layout is None:
        layout = PodcastLayout(video=VideoLayout(rect={'x': 0, 'y': 0, 'width': 1, 'height': 1}))
    else:
        layout = request.layout.model_copy(deep=True)
    layout.render_version = 2
    layout.title.text = request.title if layout.title.text is None else layout.title.text
    return request.model_copy(update={'layout': layout})


def edit_config(job: PodcastJob) -> EditConfig:
    request = source_request(job)
    config = EditConfig(
        can_edit=False,
        aspect_ratio=request.aspect_ratio,
        layout=request.layout,
        sentences=request.sentences,
        burn_subtitles=request.burn_subtitles,
    )
    if job.status != 'SUCCEEDED':
        return config.model_copy(update={'unavailable_reason': 'SOURCE_NOT_READY'})
    if getattr(job, 'base_video_key', None) and job.media_metadata:
        return config.model_copy(
            update={
                'can_edit': True,
                'duration_ms': job.media_metadata['duration_ms'],
                'sentences': [Sentence.model_validate(item) for item in job.media_metadata['sentences']],
                'base_video_url': f'/api/podcast-jobs/{job.id}/base-video',
                'download_url': f'/api/podcast-jobs/{job.id}/download',
                'current_render_id': job.current_render_id,
                'active_render_id': job.active_render_id,
                'burn_subtitles': True,
            }
        )
    directory = source_directory(job.id)
    count = job.progress.get('completed', 0)
    files = [directory / 'audio', *(directory / f'clip-{index}.mp4' for index in range(count))]
    try:
        if count <= 0 or any(not path.is_file() or path.stat().st_size == 0 for path in files):
            return config.model_copy(update={'unavailable_reason': 'SOURCE_MEDIA_UNAVAILABLE'})
        duration = media.audio_duration(directory)
        clips = media.plan(request, duration)
        aligned = media.align_timeline(request, duration)
        sentences = [
            Sentence(
                start_time=round(item.start_time),
                end_time=round(item.end_time),
                text=item.text,
                words=item.words,
            )
            for item in aligned.sentences
        ]
    except (OSError, ValueError, RuntimeError):
        return config.model_copy(update={'unavailable_reason': 'SOURCE_MEDIA_UNAVAILABLE'})
    if count != len(clips):
        return config.model_copy(update={'unavailable_reason': 'SOURCE_MEDIA_UNAVAILABLE'})
    elapsed = 0.0
    segments = []
    for index, (_, length) in enumerate(clips):
        start = round(elapsed * 1000)
        elapsed += length
        segments.append(
            EditSegment(
                index=index,
                start_time=start,
                end_time=round(elapsed * 1000),
                video_url=f'/api/podcast-jobs/{job.id}/segments/{index}/video',
            )
        )
    return config.model_copy(
        update={
            'can_edit': True,
            'duration_ms': round(duration * 1000),
            'sentences': sentences,
            'segments': segments,
        }
    )


def require_editable(config: EditConfig) -> None:
    if not config.can_edit:
        code = config.unavailable_reason or 'SOURCE_MEDIA_UNAVAILABLE'
        message = 'Original job is not ready' if code == 'SOURCE_NOT_READY' else 'Clean source media is unavailable'
        raise APIError(409, code, message)


async def saved_config(job: PodcastJob, session) -> EditConfig:
    config = await asyncio.to_thread(edit_config, job)
    if getattr(job, 'current_render_id', None):
        current = await session.scalar(
            select(PodcastRender).where(
                PodcastRender.id == job.current_render_id,
                PodcastRender.source_job_id == job.id,
            )
        )
        request = CreatePodcast.model_validate(current.payload['request'])
        config = config.model_copy(
            update={
                'layout': request.layout,
                'sentences': request.sentences,
                'burn_subtitles': request.burn_subtitles,
            }
        )
    if getattr(job, 'active_render_id', None):
        active = await session.scalar(
            select(PodcastRender).where(
                PodcastRender.id == job.active_render_id,
                PodcastRender.source_job_id == job.id,
            )
        )
        config = config.model_copy(update={'active_edit': CreateRender.model_validate(active.payload['edit'])})
    return config


def edited_request(job: PodcastJob, edit: CreateRender, config: EditConfig) -> CreatePodcast:
    require_editable(config)
    request = source_request(job)
    layout = config.layout.model_dump()
    layout.update(title=edit.title.model_dump(), subtitles=edit.subtitles.model_dump())
    sentences = [item.model_dump() for item in config.sentences]
    if edit.subtitle_texts is not None:
        if len(edit.subtitle_texts) != len(sentences):
            raise APIError(422, 'SUBTITLE_COUNT_MISMATCH', 'Subtitle count must match the original sentences')
        for sentence, text in zip(sentences, edit.subtitle_texts, strict=True):
            sentence['text'] = text
    try:
        return CreatePodcast.model_validate(
            {
                **request.model_dump(mode='json'),
                'layout': layout,
                'sentences': sentences,
                'burn_subtitles': edit.burn_subtitles,
            }
        )
    except ValidationError:
        raise APIError(422, 'LAYOUT_INVALID', 'Invalid text, layout or timeline') from None


def validate_render_preview(request: CreatePodcast):
    try:
        return preview_layout(
            PreviewLayout(
                aspect_ratio=request.aspect_ratio,
                title=request.title,
                layout=request.layout,
                sentences=request.sentences if request.burn_subtitles else [],
            )
        )
    except OSError:
        raise APIError(503, 'LAYOUT_FONT_UNAVAILABLE', 'Shared layout font is unavailable') from None
    except ValueError as error:
        raise APIError(422, 'LAYOUT_INVALID', str(error)) from None
