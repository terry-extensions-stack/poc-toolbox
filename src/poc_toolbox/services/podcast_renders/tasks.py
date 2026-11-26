import asyncio
import logging
import shutil

from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from poc_toolbox.api.podcast_contracts import CreatePodcast
from poc_toolbox.clients.podcast_storage import download_video, upload
from poc_toolbox.config import DatabaseSettings
from poc_toolbox.config.podcast import PodcastSettings
from poc_toolbox.services.podcast_database import JobLockUnavailableError, JobState
from poc_toolbox.services.podcast_media import assemble
from poc_toolbox.services.podcast_queue import celery_app
from poc_toolbox.services.podcast_renders import source_directory
from poc_toolbox.services.podcast_renders.database import RenderDatabase
from poc_toolbox.services.podcast_renders.media import render_base

logger = logging.getLogger(__name__)


def copy_inputs(payload: dict, directory: Path) -> None:
    source = source_directory(UUID(payload['source_job_id']))
    inputs = ['audio', *(f'clip-{index}.mp4' for index in range(payload['clip_count']))]
    if any(not (source / name).is_file() for name in inputs):
        raise FileNotFoundError('Clean source media is unavailable; original video was preserved')
    directory.mkdir(parents=True, exist_ok=True)
    for name in inputs:
        origin = source / name
        destination = directory / name
        if destination.is_file() and destination.stat().st_size == origin.stat().st_size:
            continue
        try:
            destination.hardlink_to(origin)
        except OSError:
            partial = destination.with_suffix('.part')
            shutil.copyfile(origin, partial)
            partial.replace(destination)


async def process_render(store: RenderDatabase, state: JobState) -> None:
    if state.status not in {'QUEUED', 'RUNNING'}:
        return
    payload = state.payload
    directory = source_directory(UUID(payload['source_job_id'])) / 'renders' / str(state.id)
    try:
        state.status, state.error = 'RUNNING', None
        state.progress = {'stage': 'COMPOSING'}
        await store.save(state)
        if 'base_video_key' in payload:
            download_video(payload['base_video_key'], directory / 'base.mp4')
        else:
            copy_inputs(payload, directory)
        request = CreatePodcast.model_validate(payload['request'])
        output = (
            render_base(directory, request, payload['duration_ms'] / 1000)
            if 'base_video_key' in payload
            else assemble(directory, request, payload['clip_count'], payload['duration_ms'] / 1000)
        )
        state.progress = {'stage': 'UPLOADING'}
        await store.save(state)
        state.output_key = upload(output, f'{payload["source_job_id"]}/edited-{state.id}.mp4')
        state.status, state.progress = 'SUCCEEDED', {'stage': 'DONE'}
        await store.save(state)
    except JobLockUnavailableError:
        raise
    except Exception:
        logger.exception('Podcast render failed: render_id=%s', state.id)
        if store.exhausted:
            raise
        if state.output_key:
            state.progress = {**state.progress, 'cleanup_keys': [state.output_key]}
            state.output_key = None
        state.status, state.error = 'FAILED', 'Composition failed; check source media and worker logs'
        await store.save(state)
        raise


async def execute_render(render_id: UUID) -> None:
    database = create_async_engine(
        DatabaseSettings().database_url.get_secret_value(),
        poolclass=NullPool,
        hide_parameters=True,
    )
    store = RenderDatabase(database, render_id, PodcastSettings().database_retry_timeout_seconds)
    try:
        state = await store.load()
        if state is not None:
            await process_render(store, state)
    except JobLockUnavailableError:
        logger.info('Render is owned by another worker: render_id=%s', render_id)
    finally:
        await store.close()
        await database.dispose()


@celery_app.task(name='podcasts.render')
def run_render(render_id: str) -> None:
    asyncio.run(execute_render(UUID(render_id)))
