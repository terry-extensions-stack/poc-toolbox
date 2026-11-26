from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from kombu.exceptions import OperationalError
from starlette.concurrency import run_in_threadpool

from poc_toolbox.api.dependencies import SessionDependency
from poc_toolbox.api.errors import APIError
from poc_toolbox.api.podcast_lookup import require_job
from poc_toolbox.clients.podcast_storage import signed_download
from poc_toolbox.services.podcast_queue import celery_app
from poc_toolbox.services.podcast_renders import edit_config, require_editable

router = APIRouter()


@router.get('/{job_id}/base-video')
async def base_video(job_id: UUID, session: SessionDependency) -> RedirectResponse:
    job = await require_job(session, job_id)
    if not job.base_video_key:
        raise APIError(409, 'SOURCE_MEDIA_UNAVAILABLE', 'Clean base video is unavailable')
    response = RedirectResponse(await run_in_threadpool(signed_download, job.base_video_key), status_code=307)
    response.headers['Cache-Control'] = 'no-store'
    return response


@router.post('/{job_id}/base-video', status_code=202)
async def convert_base_video(job_id: UUID, session: SessionDependency) -> dict:
    job = await require_job(session, job_id, lock=True)
    if job.base_video_key:
        return {'status': 'SUCCEEDED', 'base_video_url': f'/api/podcast-jobs/{job_id}/base-video'}
    config = await run_in_threadpool(edit_config, job)
    require_editable(config)
    job.media_metadata = {'conversion_status': 'QUEUED'}
    await session.commit()
    try:
        await run_in_threadpool(celery_app.send_task, 'podcasts.convert_base', args=[str(job_id)], retry=False)
    except (OperationalError, OSError):
        raise APIError(503, 'QUEUE_UNAVAILABLE', 'Conversion saved; queue delivery was not confirmed') from None
    return {'status': 'QUEUED', 'base_video_url': None}
