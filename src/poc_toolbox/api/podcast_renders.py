import hashlib
import json

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Header
from fastapi.responses import RedirectResponse
from kombu.exceptions import OperationalError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from starlette.concurrency import run_in_threadpool

from poc_toolbox.api.dependencies import PaginationDependency, SessionDependency
from poc_toolbox.api.errors import APIError
from poc_toolbox.api.podcast_base_video import router as base_video_router
from poc_toolbox.api.podcast_lookup import require_job
from poc_toolbox.api.podcast_preview_contracts import LayoutPreview
from poc_toolbox.api.podcast_render_contracts import CreateRender, EditConfig, RenderPage, RenderResponse
from poc_toolbox.clients.podcast_storage import signed_download
from poc_toolbox.db_models.podcast_render import PodcastRender
from poc_toolbox.services.podcast_queue import celery_app
from poc_toolbox.services.podcast_renders import (
    edit_config,
    edited_request,
    require_editable,
    saved_config,
    validate_render_preview,
)

router = APIRouter()
router.include_router(base_video_router)


def describe_render(render: PodcastRender, current_render_id: UUID | None = None) -> dict:
    prefix = f'/api/podcast-jobs/{render.source_job_id}/renders/{render.id}'
    return {
        'id': render.id,
        'source_job_id': render.source_job_id,
        'status': render.status,
        'progress': render.progress,
        'error': render.error,
        'edit': render.payload['edit'],
        'is_current': render.id == current_render_id,
        'download_url': f'{prefix}/download' if render.status == 'SUCCEEDED' and render.output_key else None,
    }


async def require_render(session: SessionDependency, job_id: UUID, render_id: UUID) -> PodcastRender:
    render = await session.scalar(
        select(PodcastRender).where(
            PodcastRender.id == render_id,
            PodcastRender.source_job_id == job_id,
        )
    )
    if render is None:
        raise APIError(404, 'NOT_FOUND', 'Podcast render not found')
    return render


async def enqueue_render(render_id: UUID) -> None:
    try:
        await run_in_threadpool(celery_app.send_task, 'podcasts.render', args=[str(render_id)], retry=False)
    except (OperationalError, OSError):
        raise APIError(
            503,
            'QUEUE_UNAVAILABLE',
            'Render saved but queue delivery was not confirmed; repeat the same request and Idempotency-Key',
        ) from None


@router.get('/{job_id}/edit-config', response_model=EditConfig)
async def get_edit_config(job_id: UUID, session: SessionDependency) -> EditConfig:
    return await saved_config(await require_job(session, job_id), session)


@router.post('/{job_id}/renders/preview', response_model=LayoutPreview)
async def preview_render(job_id: UUID, edit: CreateRender, session: SessionDependency) -> LayoutPreview:
    job = await require_job(session, job_id)
    config = await saved_config(job, session)
    request = edited_request(job, edit, config)
    return await run_in_threadpool(validate_render_preview, request)


@router.post('/{job_id}/renders', status_code=202, response_model=RenderResponse)
async def create_render(
    job_id: UUID,
    edit: CreateRender,
    session: SessionDependency,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=200)],
) -> dict:
    job = await require_job(session, job_id, lock=True)
    digest = hashlib.sha256(json.dumps(edit.model_dump(mode='json'), sort_keys=True).encode()).hexdigest()
    condition = (PodcastRender.source_job_id == job_id, PodcastRender.idempotency_key == idempotency_key)
    render = await session.scalar(select(PodcastRender).where(*condition))
    if render is None:
        if getattr(job, 'active_render_id', None):
            raise APIError(409, 'RENDER_IN_PROGRESS', 'A video save is already in progress')
        if not getattr(job, 'base_video_key', None):
            raise APIError(409, 'BASE_VIDEO_REQUIRED', 'Convert the original clean media to a base video first')
        config = await saved_config(job, session)
        require_editable(config)
        request = edited_request(job, edit, config)
        await run_in_threadpool(validate_render_preview, request)
        payload = {
            'source_job_id': str(job_id),
            'duration_ms': config.duration_ms,
            'clip_count': len(config.segments),
            'request': request.model_dump(mode='json'),
            'edit': edit.model_dump(mode='json'),
            'base_video_key': job.base_video_key,
        }
        await session.execute(
            insert(PodcastRender)
            .values(
                id=uuid4(),
                source_job_id=job_id,
                idempotency_key=idempotency_key,
                request_hash=digest,
                payload=payload,
                status='QUEUED',
                progress={'stage': 'QUEUED'},
            )
            .on_conflict_do_nothing(constraint='uq_podcast_render_submission')
        )
        render = await session.scalar(select(PodcastRender).where(*condition))
        job.active_render_id = render.id
    if render.request_hash != digest:
        raise APIError(422, 'IDEMPOTENCY_KEY_REUSED', 'Idempotency key reused with different parameters')
    response = describe_render(render, getattr(job, 'current_render_id', None))
    render_id, queued = render.id, render.status == 'QUEUED'
    await session.commit()
    if queued:
        await enqueue_render(render_id)
    return response


@router.get('/{job_id}/renders', response_model=RenderPage)
async def list_renders(job_id: UUID, session: SessionDependency, pagination: PaginationDependency) -> dict:
    job = await require_job(session, job_id)
    condition = PodcastRender.source_job_id == job_id
    renders = await session.scalars(
        select(PodcastRender)
        .where(condition)
        .order_by(
            PodcastRender.created_at.desc(),
            PodcastRender.id,
        )
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    total = await session.scalar(select(func.count()).select_from(PodcastRender).where(condition))
    return {
        'items': [describe_render(render, getattr(job, 'current_render_id', None)) for render in renders],
        'total': total,
        'page': pagination.page,
        'page_size': pagination.page_size,
    }


@router.get('/{job_id}/renders/{render_id}', response_model=RenderResponse)
async def get_render(job_id: UUID, render_id: UUID, session: SessionDependency) -> dict:
    job = await require_job(session, job_id)
    return describe_render(await require_render(session, job_id, render_id), job.current_render_id)


@router.get('/{job_id}/renders/{render_id}/download')
async def download_render(job_id: UUID, render_id: UUID, session: SessionDependency) -> RedirectResponse:
    render = await require_render(session, job_id, render_id)
    if render.status == 'SUCCEEDED' and not render.output_key:
        raise APIError(410, 'VIDEO_REPLACED', 'This video has been replaced by a newer save')
    if render.status != 'SUCCEEDED' or not render.output_key:
        raise APIError(409, 'VIDEO_NOT_READY', 'Render is not ready')
    return RedirectResponse(await run_in_threadpool(signed_download, render.output_key), status_code=307)


@router.post('/{job_id}/renders/{render_id}/retry', status_code=202, response_model=RenderResponse)
async def retry_render(job_id: UUID, render_id: UUID, session: SessionDependency) -> dict:
    job = await require_job(session, job_id, lock=True)
    if getattr(job, 'active_render_id', None) not in {None, render_id}:
        raise APIError(409, 'RENDER_IN_PROGRESS', 'A video save is already in progress')
    render = await session.scalar(
        select(PodcastRender)
        .where(
            PodcastRender.id == render_id,
            PodcastRender.source_job_id == job_id,
        )
        .with_for_update()
    )
    if render is None:
        raise APIError(404, 'NOT_FOUND', 'Podcast render not found')
    if render.status not in {'FAILED', 'QUEUED'}:
        raise APIError(409, 'RENDER_NOT_RETRYABLE', 'Only failed or queued renders can retry')
    config = await run_in_threadpool(edit_config, job)
    require_editable(config)
    if 'base_video_key' in render.payload:
        job.active_render_id = render.id
    render.status, render.error, render.progress = 'QUEUED', None, {'stage': 'QUEUED'}
    response = describe_render(render)
    await session.commit()
    await enqueue_render(render_id)
    return response
