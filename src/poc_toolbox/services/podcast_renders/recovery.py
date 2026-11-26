import asyncio
import logging

from uuid import UUID

from sqlalchemy import select

from poc_toolbox.clients.podcast_storage import delete_video
from poc_toolbox.config.podcast import PodcastSettings
from poc_toolbox.db_models.podcast import PodcastJob
from poc_toolbox.db_models.podcast_render import PodcastRender
from poc_toolbox.services.podcast_database import JobLockUnavailableError
from poc_toolbox.services.podcast_queue import celery_app
from poc_toolbox.services.podcast_renders.database import RenderDatabase
from poc_toolbox.services.podcast_tasks import engine

logger = logging.getLogger(__name__)


async def recover_pending() -> None:
    database = engine()
    store = RenderDatabase(database, UUID(int=0), PodcastSettings().database_retry_timeout_seconds)
    try:
        async with store.sessions() as session:
            statements = (
                (select(PodcastRender.id).where(PodcastRender.status.in_(['QUEUED', 'RUNNING'])), 'podcasts.render'),
                (select(PodcastRender.id).where(PodcastRender.progress.op('?')('cleanup_keys')), 'podcasts.cleanup'),
                (
                    select(PodcastJob.id).where(
                        PodcastJob.base_video_key.is_(None),
                        PodcastJob.media_metadata['conversion_status'].as_string() == 'QUEUED',
                    ),
                    'podcasts.convert_base',
                ),
            )
            for statement, task in statements:
                rows = await session.stream_scalars(statement.execution_options(yield_per=100))
                async for record_id in rows:
                    celery_app.send_task(task, args=[str(record_id)], retry=False)
    finally:
        await database.dispose()


async def cleanup_render(render_id: UUID) -> None:
    database = engine()
    store = RenderDatabase(database, render_id, PodcastSettings().database_retry_timeout_seconds)
    try:
        state = await store.load()
        if state is None or not state.progress.get('cleanup_keys'):
            return
        for key in state.progress['cleanup_keys']:
            delete_video(key)

        async def clear():
            async with store.sessions() as session, session.begin():
                record = await session.get(PodcastRender, render_id)
                progress = dict(record.progress)
                progress.pop('cleanup_keys', None)
                record.progress = progress

        await store.run(clear)
    except JobLockUnavailableError:
        logger.info('Cleanup already running: render_id=%s', render_id)
    except Exception:
        logger.exception('Superseded video cleanup failed; retained for recovery: render_id=%s', render_id)
        raise
    finally:
        await store.close()
        await database.dispose()


@celery_app.task(name='podcasts.recover')
def recover() -> None:
    asyncio.run(recover_pending())


@celery_app.task(name='podcasts.cleanup')
def cleanup(render_id: str) -> None:
    asyncio.run(cleanup_render(UUID(render_id)))
