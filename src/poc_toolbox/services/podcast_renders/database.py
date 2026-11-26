from uuid import UUID

from sqlalchemy import select

from poc_toolbox.db_models.podcast import PodcastJob
from poc_toolbox.db_models.podcast_render import PodcastRender
from poc_toolbox.services.podcast_database import JobLockUnavailableError, JobState, PodcastDatabase


class RenderDatabase(PodcastDatabase):
    record_model = PodcastRender

    async def save(self, state: JobState) -> None:
        if state.status not in {'SUCCEEDED', 'FAILED'} or 'base_video_key' not in state.payload:
            await super().save(state)
            return

        async def publish():
            async with self.sessions() as session, session.begin():
                job = await session.scalar(
                    select(PodcastJob).where(PodcastJob.id == UUID(state.payload['source_job_id'])).with_for_update()
                )
                record = await session.get(PodcastRender, state.id)
                if record.status == state.status and record.output_key == state.output_key:
                    return
                if job.active_render_id != state.id:
                    raise JobLockUnavailableError('Render no longer owns the publication slot')
                if state.status == 'SUCCEEDED':
                    await replace_current(session, job, state)
                record.status, record.error = state.status, state.error
                record.output_key, record.progress = state.output_key, dict(state.progress)
                job.active_render_id = None

        await self.run(publish)


async def replace_current(session, job: PodcastJob, state: JobState) -> None:
    previous = await session.get(PodcastRender, job.current_render_id) if job.current_render_id else None
    if job.output_key and job.output_key != job.base_video_key:
        state.progress = {**state.progress, 'cleanup_keys': [job.output_key]}
    if previous is not None and previous.output_key:
        previous.output_key = None
    job.current_render_id, job.output_key = state.id, state.output_key
