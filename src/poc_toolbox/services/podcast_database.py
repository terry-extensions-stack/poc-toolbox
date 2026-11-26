import asyncio
import errno
import logging
import time

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from poc_toolbox.db_models.podcast import PodcastJob

logger = logging.getLogger(__name__)
Result = TypeVar('Result')
RETRY_DELAYS = (2, 4, 8, 16, 20)
CONNECT_TIMEOUT = 10
CONNECTION_ERRNOS = {
    errno.ECONNREFUSED,
    errno.ECONNRESET,
    errno.EHOSTUNREACH,
    errno.ENETUNREACH,
    errno.ETIMEDOUT,
    errno.EPIPE,
}


def connection_error(error: Exception) -> bool:
    if isinstance(error, (ConnectionError, TimeoutError)):
        return True
    if isinstance(error, OSError) and error.errno in CONNECTION_ERRNOS:
        return True
    if isinstance(error, DBAPIError):
        return error.connection_invalidated or connection_error(error.orig)
    code = getattr(error, 'sqlstate', None)
    return bool(code and (code.startswith('08') or code in {'57P01', '57P02', '57P03', '53300'}))


class JobLockUnavailableError(RuntimeError):
    pass


@dataclass
class JobState:
    id: UUID
    payload: dict
    progress: dict
    status: str
    error: str | None = None
    output_key: str | None = None
    base_video_key: str | None = None
    media_metadata: dict | None = None
    workflow_version: int = 1

    @classmethod
    def from_record(cls, job: PodcastJob) -> 'JobState':
        state = cls(job.id, dict(job.payload), dict(job.progress), job.status, job.error, job.output_key)
        if isinstance(job, PodcastJob):
            state.base_video_key = job.base_video_key
            state.media_metadata = job.media_metadata
            state.workflow_version = job.workflow_version
        return state


class PodcastDatabase:
    record_model = PodcastJob

    def __init__(self, database: AsyncEngine, job_id: UUID, timeout: float):
        self.database = database
        self.job_id = job_id
        self.timeout = timeout
        self.lock_id = job_id.int % (2**63 - 1)
        self.lock = None
        self.exhausted = False
        self.sessions = async_sessionmaker(database, expire_on_commit=False)

    async def ensure_lock(self) -> None:
        if self.lock is not None:
            try:
                await self.lock.scalar(text('SELECT 1'))
                return
            except BaseException:
                await self.close()
                raise
        self.lock = await self.database.connect()
        try:
            await self.lock.execution_options(isolation_level='AUTOCOMMIT')
            acquired = await self.lock.scalar(text('SELECT pg_try_advisory_lock(:id)'), {'id': self.lock_id})
            if not acquired:
                await self.close()
                raise JobLockUnavailableError(f'Podcast job {self.job_id} is owned by another worker')
        except BaseException:
            await self.close()
            raise

    async def run(self, operation: Callable[[], Awaitable[Result]]) -> Result:
        deadline = time.monotonic() + self.timeout
        first_error = None
        attempt = 0
        self.exhausted = False
        while True:
            remaining = deadline - time.monotonic()
            try:
                async with asyncio.timeout(min(CONNECT_TIMEOUT, max(0, remaining))):
                    await self.ensure_lock()
                    return await operation()
            except Exception as error:
                if not connection_error(error):
                    raise
                first_error = first_error or error
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.exhausted = True
                    logger.error(
                        'Podcast database retry exhausted: job_id=%s error_type=%s',
                        self.job_id,
                        type(first_error).__name__,
                    )
                    raise first_error from None
                delay = min(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)], remaining)
                attempt += 1
                logger.warning(
                    'Podcast database connection retry: job_id=%s attempt=%s delay=%.2fs remaining=%.2fs error_type=%s',
                    self.job_id,
                    attempt,
                    delay,
                    remaining,
                    type(error).__name__,
                )
                await asyncio.sleep(delay)
                if time.monotonic() >= deadline:
                    self.exhausted = True
                    logger.error('Podcast database retry exhausted: job_id=%s', self.job_id)
                    raise first_error from None

    async def check(self) -> None:
        async def healthy():
            return None

        await self.run(healthy)

    async def load(self) -> JobState | None:
        async def read():
            async with self.sessions() as session:
                job = await session.get(self.record_model, self.job_id)
                return JobState.from_record(job) if job is not None else None

        return await self.run(read)

    async def save(self, state: JobState) -> None:
        progress = dict(state.progress)
        status, error, output_key = state.status, state.error, state.output_key

        async def write():
            async with self.sessions() as session, session.begin():
                job = await session.get(self.record_model, self.job_id)
                if job is None:
                    raise ValueError('Podcast job no longer exists')
                if job.status not in {'QUEUED', 'RUNNING'} or job.progress.get('completed', 0) > progress.get(
                    'completed', 0
                ):
                    raise JobLockUnavailableError('Podcast job was advanced by another execution')
                job.progress, job.status, job.error, job.output_key = progress, status, error, output_key
                if isinstance(job, PodcastJob):
                    job.base_video_key, job.media_metadata = state.base_video_key, state.media_metadata

        await self.run(write)

    async def close(self) -> None:
        lock, self.lock = self.lock, None
        if lock is None:
            return
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                await lock.close()
        except Exception:
            logger.warning('Podcast lock connection cleanup failed: job_id=%s', self.job_id)
