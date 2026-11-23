from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from poc_toolbox.ai_config_encryption import encrypt_api_key
from poc_toolbox.db_models import AIModelConfig
from poc_toolbox.repositories.contracts import (
    CreateModelConfig,
    EncryptionConfigurationError,
    Pagination,
    UpdateModelConfig,
)


def _encrypt_key(api_key: str) -> str:
    try:
        return encrypt_api_key(api_key)
    except ValueError:
        raise EncryptionConfigurationError('API key encryption is unavailable') from None


class AIModelConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, request: CreateModelConfig) -> AIModelConfig:
        config = AIModelConfig(
            name=request.name,
            base_url=str(request.base_url),
            model_id=request.model_id,
            api_key_ciphertext=_encrypt_key(request.api_key.get_secret_value()),
        )
        self.session.add(config)
        await self.session.flush()
        await self.session.refresh(config)
        return config

    async def find_by_id(self, config_id: UUID) -> AIModelConfig | None:
        return await self.session.get(AIModelConfig, config_id)

    async def find_by_name(self, name: str) -> AIModelConfig | None:
        return await self.session.scalar(select(AIModelConfig).where(AIModelConfig.name == name))

    async def list(self, pagination: Pagination) -> tuple[list[AIModelConfig], int]:
        query = select(AIModelConfig).order_by(AIModelConfig.created_at, AIModelConfig.id)
        records = await self.session.scalars(query.offset(pagination.offset).limit(pagination.page_size))
        total = await self.session.scalar(select(func.count()).select_from(AIModelConfig))
        return list(records), total or 0

    async def update(self, config_id: UUID, request: UpdateModelConfig) -> AIModelConfig | None:
        config = await self.find_by_id(config_id)
        if config is None:
            return None
        changes = request.model_dump(exclude_unset=True, exclude={'api_key', 'base_url'})
        if request.api_key is not None:
            changes['api_key_ciphertext'] = _encrypt_key(request.api_key.get_secret_value())
        if request.base_url is not None:
            changes['base_url'] = str(request.base_url)
        for name, value in changes.items():
            setattr(config, name, value)
        await self.session.flush()
        await self.session.refresh(config)
        return config

    async def delete(self, config_id: UUID) -> None:
        config = await self.find_by_id(config_id)
        if config is not None:
            await self.session.delete(config)
            await self.session.flush()
