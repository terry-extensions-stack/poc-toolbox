from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from poc_toolbox.db_models import AITemplate
from poc_toolbox.repositories.contracts import CreateTemplate, Pagination, UpdateTemplate


class AITemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, request: CreateTemplate) -> AITemplate:
        template = AITemplate(**request.model_dump())
        self.session.add(template)
        await self.session.flush()
        await self.session.refresh(template, attribute_names=['model_config', 'created_at', 'updated_at'])
        return template

    async def find_by_id(self, template_id: UUID) -> AITemplate | None:
        query = select(AITemplate).options(joinedload(AITemplate.model_config)).where(AITemplate.id == template_id)
        return await self.session.scalar(query)

    async def find_by_name(self, name: str) -> AITemplate | None:
        query = select(AITemplate).options(joinedload(AITemplate.model_config)).where(AITemplate.name == name)
        return await self.session.scalar(query)

    async def list(self, pagination: Pagination, model_config_id: UUID | None = None) -> tuple[list[AITemplate], int]:
        query = select(AITemplate).options(joinedload(AITemplate.model_config))
        count = select(func.count()).select_from(AITemplate)
        if model_config_id is not None:
            query = query.where(AITemplate.model_config_id == model_config_id)
            count = count.where(AITemplate.model_config_id == model_config_id)
        query = query.order_by(AITemplate.created_at, AITemplate.id)
        records = await self.session.scalars(query.offset(pagination.offset).limit(pagination.page_size))
        total = await self.session.scalar(count)
        return list(records), total or 0

    async def update(self, template_id: UUID, request: UpdateTemplate) -> AITemplate | None:
        template = await self.find_by_id(template_id)
        if template is None:
            return None
        for name, value in request.model_dump(exclude_unset=True).items():
            setattr(template, name, value)
        await self.session.flush()
        await self.session.refresh(template, attribute_names=['model_config', 'created_at', 'updated_at'])
        return template

    async def delete(self, template_id: UUID) -> None:
        template = await self.find_by_id(template_id)
        if template is not None:
            await self.session.delete(template)
            await self.session.flush()
