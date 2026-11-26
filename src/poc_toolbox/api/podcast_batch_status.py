from fastapi import APIRouter
from sqlalchemy import func, select

from poc_toolbox.api.dependencies import SessionDependency
from poc_toolbox.api.podcast_contracts import PodcastBatchStatusRequest, PodcastBatchStatusResponse
from poc_toolbox.db_models.podcast import PodcastJob

router = APIRouter()


@router.post('/batch-status', response_model=PodcastBatchStatusResponse)
async def batch_job_status(request: PodcastBatchStatusRequest, session: SessionDependency) -> dict:
    """Return every input podcast ID with its newest task status, using a null status when missing."""
    podcast_id = PodcastJob.payload['id'].as_string()
    latest = (
        select(
            podcast_id.label('id'),
            PodcastJob.status,
            func.row_number()
            .over(
                partition_by=podcast_id,
                order_by=(PodcastJob.created_at.desc().nulls_last(), PodcastJob.id.desc()),
            )
            .label('position'),
        )
        .where(podcast_id.in_([str(identifier) for identifier in request.ids]))
        .subquery()
    )
    jobs = await session.execute(select(latest.c.id, latest.c.status).where(latest.c.position == 1))
    statuses = {job.id: job.status for job in jobs}
    return {'items': [{'id': str(podcast_id), 'status': statuses.get(str(podcast_id))} for podcast_id in request.ids]}
