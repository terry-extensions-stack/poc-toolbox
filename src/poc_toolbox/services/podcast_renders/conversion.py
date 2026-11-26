import asyncio
import logging

from uuid import UUID

from sqlalchemy import select

from poc_toolbox.clients.podcast_storage import upload
from poc_toolbox.config.podcast import PodcastSettings
from poc_toolbox.db_models.podcast import PodcastJob
from poc_toolbox.services import podcast_media as media
from poc_toolbox.services.podcast_database import JobLockUnavailableError, PodcastDatabase
from poc_toolbox.services.podcast_queue import celery_app
from poc_toolbox.services.podcast_renders import edit_config, require_editable, source_directory
from poc_toolbox.services.podcast_renders.source import source_request
from poc_toolbox.services.podcast_tasks import engine

logger = logging.getLogger(__name__)


async def convert_source(job_id: UUID) -> None:
    database = engine()
    store = PodcastDatabase(database, job_id, PodcastSettings().database_retry_timeout_seconds)
    try:
        await store.check()
        async with store.sessions() as session:
            job = await session.get(PodcastJob, job_id)
            if job is None or job.base_video_key:
                return
            config = edit_config(job)
            require_editable(config)
            request = source_request(job)
        directory = source_directory(job_id)
        output = media.assemble_base(directory, request, len(config.segments), config.duration_ms / 1000)
        key = upload(output, f'{job_id}/base.mp4')
        metadata = media.base_metadata(request, config.duration_ms / 1000)
        await update_conversion(store, {'base_video_key': key, 'media_metadata': metadata})
    except JobLockUnavailableError:
        logger.info('Base conversion already running: job_id=%s', job_id)
    except Exception:
        logger.exception('Base conversion failed: job_id=%s', job_id)
        if not store.exhausted:
            await update_conversion(store, {'media_metadata': {'conversion_status': 'FAILED'}})
        raise
    finally:
        await store.close()
        await database.dispose()


async def update_conversion(store: PodcastDatabase, values: dict) -> None:
    async def write():
        async with store.sessions() as session, session.begin():
            job = await session.scalar(select(PodcastJob).where(PodcastJob.id == store.job_id).with_for_update())
            if job.base_video_key:
                return
            for name, value in values.items():
                setattr(job, name, value)

    await store.run(write)


@celery_app.task(name='podcasts.convert_base', autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True)
def convert_base(job_id: str) -> None:
    asyncio.run(convert_source(UUID(job_id)))
