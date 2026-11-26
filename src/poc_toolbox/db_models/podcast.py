from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from poc_toolbox.db_models import BaseModel


class PodcastJob(BaseModel):
    __tablename__ = 'podcast_jobs'
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
    model_config_id: Mapped[UUID | None] = mapped_column(ForeignKey('ai_model_configs.id', ondelete='RESTRICT'))
    status: Mapped[str] = mapped_column(String(30), default='QUEUED', index=True)
    progress: Mapped[dict] = mapped_column(JSONB, default=dict)
    output_key: Mapped[str | None] = mapped_column(Text)
    base_video_key: Mapped[str | None] = mapped_column(Text)
    media_metadata: Mapped[dict | None] = mapped_column(JSONB)
    workflow_version: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    current_render_id: Mapped[UUID | None] = mapped_column()
    active_render_id: Mapped[UUID | None] = mapped_column()
    error: Mapped[str | None] = mapped_column(Text)
