from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from poc_toolbox.database import get_session
from poc_toolbox.repositories import AIModelConfigRepository, AITemplateRepository, Pagination

SessionDependency = Annotated[AsyncSession, Depends(get_session, scope='function')]


def model_config_repository(session: SessionDependency) -> AIModelConfigRepository:
    return AIModelConfigRepository(session)


def template_repository(session: SessionDependency) -> AITemplateRepository:
    return AITemplateRepository(session)


def pagination(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Pagination:
    return Pagination(page, page_size)


ModelConfigRepositoryDependency = Annotated[AIModelConfigRepository, Depends(model_config_repository)]
TemplateRepositoryDependency = Annotated[AITemplateRepository, Depends(template_repository)]
PaginationDependency = Annotated[Pagination, Depends(pagination)]
