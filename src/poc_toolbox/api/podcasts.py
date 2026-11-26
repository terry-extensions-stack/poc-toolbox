import hashlib
import json

from collections.abc import AsyncIterator
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Path, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from kombu.exceptions import OperationalError
from pydantic import HttpUrl
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from poc_toolbox.api.dependencies import PaginationDependency, SessionDependency
from poc_toolbox.api.errors import APIError
from poc_toolbox.api.podcast_batch_status import router as batch_status_router
from poc_toolbox.api.podcast_contracts import CreatePodcast, PodcastPage, PodcastResponse, PodcastSegmentPage
from poc_toolbox.api.podcast_lookup import require_job
from poc_toolbox.api.podcast_preview import router as preview_router
from poc_toolbox.api.podcast_renders import router as render_router
from poc_toolbox.clients.podcast_storage import signed_download
from poc_toolbox.config.podcast import PodcastSettings
from poc_toolbox.db_models.podcast import PodcastJob
from poc_toolbox.services.podcast_queue import celery_app

router = APIRouter(prefix='/api/podcast-jobs', tags=['podcast-jobs'])
router.include_router(batch_status_router, tags=['batch_status'])
router.include_router(preview_router, tags=['preview'])
router.include_router(render_router, tags=['render'])


async def submission_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


SubmissionSession = Annotated[AsyncSession, Depends(submission_session)]


async def enqueue(job_id: UUID) -> None:
    try:
        await run_in_threadpool(celery_app.send_task, 'podcasts.run', args=[str(job_id)], retry=False)
    except (OperationalError, OSError):
        raise APIError(
            503,
            'QUEUE_UNAVAILABLE',
            'Job saved but queue delivery was not confirmed; repeat the same request and Idempotency-Key',
        ) from None


def describe(job: PodcastJob) -> dict:
    return {
        'id': str(job.id),
        'status': job.status,
        'progress': job.progress,
        'error': job.error,
        'download_url': f'/api/podcast-jobs/{job.id}/download' if job.output_key else None,
        'segments_url': f'/api/podcast-jobs/{job.id}/segments',
        'base_video_url': f'/api/podcast-jobs/{job.id}/base-video' if job.base_video_key else None,
        'current_render_id': job.current_render_id,
        'active_render_id': job.active_render_id,
        'base_video_status': (
            'SUCCEEDED' if job.base_video_key else (job.media_metadata or {}).get('conversion_status')
        ),
    }


@router.post('', status_code=202, response_model=PodcastResponse)
async def create_job(
    request: CreatePodcast,
    session: SubmissionSession,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=200)],
) -> dict:
    payload = request.model_dump(mode='json')
    if request.layout is None:
        payload.pop('layout')
    elif request.layout.render_version == 1:
        payload['layout'].pop('render_version')
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    statement = (
        insert(PodcastJob)
        .values(
            id=uuid4(),
            idempotency_key=idempotency_key,
            request_hash=digest,
            payload=payload,
            status='QUEUED',
            progress={},
            workflow_version=2,
        )
        .on_conflict_do_nothing(index_elements=['idempotency_key'])
    )
    await session.execute(statement)
    job = await session.scalar(select(PodcastJob).where(PodcastJob.idempotency_key == idempotency_key))
    if job.request_hash != digest:
        raise APIError(422, 'IDEMPOTENCY_KEY_REUSED', 'Idempotency key reused with different payload')
    response = describe(job)
    should_enqueue = job.status == 'QUEUED'
    job_id = job.id
    await session.commit()
    if should_enqueue:
        await enqueue(job_id)
    return response


@router.get('', response_model=PodcastPage)
async def list_jobs(
    session: SessionDependency,
    pagination: PaginationDependency,
    image_url: Annotated[HttpUrl | None, Query(description='Exact image URL; combined with audio_url using OR')] = None,
    audio_url: Annotated[HttpUrl | None, Query(description='Exact audio URL; combined with image_url using OR')] = None,
    idempotency_key: Annotated[
        str | None,
        Query(
            min_length=1, max_length=200, description='Exact Idempotency-Key; overrides image_url and audio_url filters'
        ),
    ] = None,
) -> dict:
    filters = [
        PodcastJob.payload[field].as_string() == str(url)
        for field, url in (('image_url', image_url), ('audio_url', audio_url))
        if url is not None
    ]
    conditions = [or_(*filters)] if filters else []
    if idempotency_key is not None:
        conditions = [PodcastJob.idempotency_key == idempotency_key]
    jobs = await session.scalars(
        select(PodcastJob)
        .where(*conditions)
        .order_by(PodcastJob.created_at.desc(), PodcastJob.id)
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    total = await session.scalar(select(func.count()).select_from(PodcastJob).where(*conditions))
    return {
        'items': [describe(job) for job in jobs],
        'total': total,
        'page': pagination.page,
        'page_size': pagination.page_size,
    }


@router.get('/{job_id}', response_model=PodcastResponse)
async def get_job(job_id: UUID, session: SessionDependency) -> dict:
    return describe(await require_job(session, job_id))


@router.post('/{job_id}/retry', status_code=202, response_model=PodcastResponse)
async def retry_job(job_id: UUID, session: SubmissionSession) -> dict:
    job = await session.scalar(select(PodcastJob).where(PodcastJob.id == job_id).with_for_update())
    if job is None:
        raise APIError(404, 'NOT_FOUND', 'Podcast job not found')
    if job.status != 'FAILED':
        raise APIError(409, 'JOB_NOT_RETRYABLE', 'Only failed jobs with known submission outcomes can retry')
    job.status, job.error = 'QUEUED', None
    response = describe(job)
    await session.commit()
    await enqueue(job_id)
    return response


@router.get('/{job_id}/download')
async def download_job(job_id: UUID, session: SessionDependency) -> RedirectResponse:
    job = await require_job(session, job_id)
    if job.status != 'SUCCEEDED' or not job.output_key:
        raise APIError(409, 'VIDEO_NOT_READY', 'Video is not ready')
    response = RedirectResponse(await run_in_threadpool(signed_download, job.output_key), status_code=307)
    response.headers['Cache-Control'] = 'no-store'
    return response


@router.get('/{job_id}/segments', response_model=PodcastSegmentPage)
async def list_segments(job_id: UUID, session: SessionDependency, pagination: PaginationDependency) -> dict:
    job = await require_job(session, job_id)
    total = job.progress.get('completed', 0)
    indices = range(pagination.offset, min(total, pagination.offset + pagination.page_size))
    prefix = f'/api/podcast-jobs/{job_id}/segments'
    return {
        'items': [
            {
                'index': index,
                'video_url': f'{prefix}/{index}/video',
                'raw_video_url': f'{prefix}/{index}/video?variant=raw',
            }
            for index in indices
        ],
        'total': total,
        'page': pagination.page,
        'page_size': pagination.page_size,
    }


@router.get('/{job_id}/segments/{index}/video')
async def segment_video(
    job_id: UUID,
    index: Annotated[int, Path(ge=0)],
    session: SessionDependency,
    variant: Literal['clip', 'raw'] = 'clip',
) -> FileResponse:
    job = await require_job(session, job_id)
    if index >= job.progress.get('completed', 0):
        raise APIError(404, 'SEGMENT_NOT_READY', 'Completed segment not found')
    path = PodcastSettings().work_dir / str(job_id) / f'{variant}-{index}.mp4'
    if not await run_in_threadpool(path.is_file):
        raise APIError(404, 'SEGMENT_UNAVAILABLE', 'Segment file is unavailable')
    return FileResponse(
        path, media_type='video/mp4', filename=f'{variant}-{index}.mp4', content_disposition_type='inline'
    )
