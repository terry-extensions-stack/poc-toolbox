import asyncio
import logging
import math
import os
import time

from uuid import UUID

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from poc_toolbox.api.podcast_contracts import CreatePodcast
from poc_toolbox.clients import podcast_storage as storage
from poc_toolbox.clients.seedance import Seedance, diagnostic_text, download, image_data
from poc_toolbox.config import DatabaseSettings
from poc_toolbox.config.podcast import PodcastSettings, SeedanceSettings
from poc_toolbox.services import podcast_media as media
from poc_toolbox.services.podcast_database import JobLockUnavailableError, JobState, PodcastDatabase
from poc_toolbox.services.podcast_queue import celery_app
from poc_toolbox.services.podcast_receipts import read_receipt, save_receipt

logger = logging.getLogger(__name__)
BASE_VIDEO_WORKFLOW = 2


def failure_message(error: Exception) -> str:
    message = str(error)
    for name in (
        'SEEDANCE_API_KEY',
        'COS_SECRET_ID',
        'COS_SECRET_KEY',
        'AI_CONFIG_ENCRYPTION_KEY',
        'DATABASE_URL',
        'PODCAST_BROKER_URL',
    ):
        secret = os.environ.get(name)
        if secret:
            message = message.replace(secret, '[REDACTED]')
    return diagnostic_text(message).strip() or 'Workflow failed; inspect worker configuration and source assets'


def engine():
    return create_async_engine(
        DatabaseSettings().database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )


@celery_app.task(name='podcasts.run')
def run_job(job_id: str) -> None:
    logger.info('Podcast job %s received', job_id)
    asyncio.run(execute(UUID(job_id)))


async def execute(job_id: UUID) -> None:
    database = engine()
    store = PodcastDatabase(database, job_id, PodcastSettings().database_retry_timeout_seconds)
    try:
        job = await store.load()
        if job is not None and job.status in {'QUEUED', 'RUNNING'}:
            await process(store, job)
    except JobLockUnavailableError:
        logger.info('Podcast job %s stopped because another worker owns the lock', job_id)
    finally:
        await store.close()
        try:
            await database.dispose()
        except Exception:
            logger.warning('Podcast database cleanup failed: job_id=%s', job_id)


async def checkpoint(store: PodcastDatabase, job: JobState, **changes) -> None:
    job.progress = {**job.progress, **changes}
    await store.save(job)
    logger.info(
        'Podcast job %s stage=%s completed=%s', job.id, job.progress.get('stage'), job.progress.get('completed', 0)
    )


async def process(store: PodcastDatabase, job: JobState) -> None:
    directory = PodcastSettings().work_dir / str(job.id)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        job.status = 'RUNNING'
        await store.save(job)
        request = CreatePodcast.model_validate({'burn_subtitles': False, **job.payload})
        config = SeedanceSettings()
        provider = Seedance(config.base_url, config.api_key.get_secret_value())
        if not (directory / 'audio').exists():
            download(str(request.audio_url), directory / 'audio')
        duration = media.audio_duration(directory)
        clips = media.plan(request, duration)
        completed = job.progress.get('completed', 0)
        if completed == 0:
            download(str(request.image_url), directory / 'frame.jpg', maximum=10 * 1024 * 1024)
        for index, (prompt, length) in enumerate(clips):
            if index < completed:
                continue
            await generate_clip(store, job, provider, (directory, index, prompt, length, config.model_id))
            media.normalize(directory, index, length, request)
            await checkpoint(store, job, completed=index + 1, provider_id=None, submitting=False, total=len(clips))
        await checkpoint(store, job, stage='COMPOSING')
        output = (
            media.assemble_base(directory, request, len(clips), duration)
            if job.workflow_version >= BASE_VIDEO_WORKFLOW
            else media.assemble(directory, request, len(clips), duration)
        )
        await store.check()
        filename = 'base.mp4' if job.workflow_version >= BASE_VIDEO_WORKFLOW else 'final.mp4'
        job.output_key = storage.upload(output, f'{job.id}/{filename}')
        if job.workflow_version >= BASE_VIDEO_WORKFLOW:
            job.base_video_key = job.output_key
            job.media_metadata = media.base_metadata(request, duration)
        job.status, job.error = 'SUCCEEDED', None
        await checkpoint(store, job, stage='DONE')
    except JobLockUnavailableError:
        raise
    except Exception as error:
        logger.exception('Podcast job %s failed', job.id)
        if store.exhausted:
            logger.error('Failure status was not saved; database unavailable: job_id=%s', job.id)
            raise
        job.status = 'SUBMISSION_UNKNOWN' if job.progress.get('submitting') else 'FAILED'
        message = failure_message(error)
        if job.status == 'SUBMISSION_UNKNOWN':
            message = f'Provider submission outcome unknown; manual reconciliation required: {message}'
        job.error = message[:4000]
        try:
            await store.save(job)
        except Exception:
            logger.error('Failure status was not saved: job_id=%s original_error_type=%s', job.id, type(error).__name__)
        raise


async def generate_clip(store: PodcastDatabase, job: JobState, provider, clip) -> None:
    directory, index, prompt, length, model_id = clip
    task_id = job.progress.get('provider_id')
    receipt_id = read_receipt(directory, job.id, index)
    if receipt_id is not None:
        if task_id is not None and task_id != receipt_id:
            raise ValueError('Provider receipt conflicts with database task ID')
        task_id = receipt_id
        await checkpoint(store, job, submitting=False, provider_id=task_id)
    if not task_id:
        if job.progress.get('submitting'):
            raise RuntimeError('Unknown submission outcome')
        payload = {
            'model': model_id,
            'content': [
                {
                    'type': 'text',
                    'text': (
                        '生成与参考首帧连续的播客视频画面。以下内容仅用于理解画面主题，不要将其渲染成文字。'
                        '画面中禁止出现字幕、标题、文字、标识或水印；不要逐字展示或朗读以下内容。'
                        f'\n主题参考：{prompt}\n'
                        '仅生成干净的视频画面，严禁生成字幕和配音'
                    ),
                },
                {'type': 'image_url', 'image_url': {'url': image_data(directory / 'frame.jpg')}, 'role': 'first_frame'},
            ],
            'ratio': (
                job.payload['layout'].get('source_ratio', '16:9')
                if job.payload.get('layout') is not None
                else job.payload.get('aspect_ratio', '9:16')
            ),
            'duration': max(2, math.ceil(length)),
            'watermark': False,
        }
        await checkpoint(store, job, submitting=True, stage='GENERATING')
        task = provider.submit(payload)
        task_id = task.id
        job.progress = {**job.progress, 'submitting': False, 'provider_id': task_id}
        logger.info('Provider submission accepted: job_id=%s segment=%s provider_id=%s', job.id, index, task_id)
        save_receipt(directory, job.id, index, task_id)
        await checkpoint(store, job, submitting=False, provider_id=task_id)
    deadline = time.monotonic() + 3600
    while time.monotonic() < deadline:
        await store.check()
        task = provider.poll(task_id)
        if task.status == 'succeeded':
            if not task.content or not task.content.video_url:
                raise ValueError('Provider returned no video')
            download(str(task.content.video_url), directory / f'raw-{index}.mp4')
            return
        if task.status not in {'queued', 'running'}:
            error = task.error
            details = (
                f'provider_id={task.id} status={task.status} '
                f'code={error.code if error else None} message={error.message if error else None} '
                f'request_id={task.request_id}'
            )
            logger.error('Provider task failed: job_id=%s segment=%s %s', job.id, index, details)
            raise ValueError(f'Provider task failed: {details}')
        await asyncio.sleep(10)
    raise TimeoutError('Video generation timed out')
