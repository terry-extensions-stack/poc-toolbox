from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from poc_toolbox.api.errors import APIError
from poc_toolbox.db_models.podcast import PodcastJob


async def require_job(session: AsyncSession, job_id: UUID, *, lock: bool = False) -> PodcastJob:
    job = await session.get(PodcastJob, job_id, with_for_update=lock, populate_existing=lock)
    if job is None:
        raise APIError(404, 'NOT_FOUND', 'Podcast job not found')
    return job
