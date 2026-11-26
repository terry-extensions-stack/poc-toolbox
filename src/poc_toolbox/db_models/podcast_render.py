from uuid import UUID

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from poc_toolbox.db_models import BaseModel


class PodcastRender(BaseModel):
    __tablename__ = 'podcast_renders'
    __table_args__ = (UniqueConstraint('source_job_id', 'idempotency_key', name='uq_podcast_render_submission'),)

    source_job_id: Mapped[UUID] = mapped_column(ForeignKey('podcast_jobs.id', ondelete='RESTRICT'), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(30), default='QUEUED', index=True)
    progress: Mapped[dict] = mapped_column(JSONB, default=dict)
    output_key: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
