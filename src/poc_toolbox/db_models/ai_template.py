from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from poc_toolbox.db_models.base import BaseModel


class AIModelConfig(BaseModel):
    __tablename__ = 'ai_model_configs'

    name: Mapped[str] = mapped_column(String(100), unique=True)
    base_url: Mapped[str] = mapped_column(String(2048))
    model_id: Mapped[str] = mapped_column(String(255))
    api_key_ciphertext: Mapped[str] = mapped_column(Text)


class AITemplate(BaseModel):
    __tablename__ = 'ai_templates'

    name: Mapped[str] = mapped_column(String(100), unique=True)
    system_prompt: Mapped[str] = mapped_column(Text, default='', server_default='')
    user_prompt: Mapped[str] = mapped_column(Text)
    model_config_id: Mapped[UUID] = mapped_column(ForeignKey('ai_model_configs.id', ondelete='RESTRICT'), index=True)
    model_config: Mapped[AIModelConfig] = relationship()
