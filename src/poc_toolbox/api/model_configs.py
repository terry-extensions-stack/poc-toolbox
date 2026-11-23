from uuid import UUID

from fastapi import APIRouter, Response

from poc_toolbox.api.dependencies import ModelConfigRepositoryDependency, PaginationDependency
from poc_toolbox.api.errors import APIError
from poc_toolbox.db_models import AIModelConfig
from poc_toolbox.repositories import CreateModelConfig, ModelConfigResponse, PageResponse, UpdateModelConfig

router = APIRouter(prefix='/api/model-configs', tags=['model-configs'])


@router.post('', response_model=ModelConfigResponse, status_code=201)
async def create_model_config(request: CreateModelConfig, repository: ModelConfigRepositoryDependency) -> AIModelConfig:
    return await repository.create(request)


@router.get('', response_model=PageResponse[ModelConfigResponse])
async def list_model_configs(
    repository: ModelConfigRepositoryDependency, pagination: PaginationDependency
) -> PageResponse[ModelConfigResponse]:
    records, total = await repository.list(pagination)
    return PageResponse(
        items=[ModelConfigResponse.model_validate(record) for record in records],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get('/{config_id}', response_model=ModelConfigResponse)
async def get_model_config(config_id: UUID, repository: ModelConfigRepositoryDependency) -> AIModelConfig:
    config = await repository.find_by_id(config_id)
    if config is None:
        raise APIError(404, 'NOT_FOUND', 'Model configuration not found')
    return config


@router.patch('/{config_id}', response_model=ModelConfigResponse)
async def update_model_config(config_id: UUID, request: UpdateModelConfig, repository: ModelConfigRepositoryDependency):
    config = await repository.update(config_id, request)
    if config is None:
        raise APIError(404, 'NOT_FOUND', 'Model configuration not found')
    return config


@router.delete('/{config_id}', status_code=204)
async def delete_model_config(config_id: UUID, repository: ModelConfigRepositoryDependency) -> Response:
    await repository.delete(config_id)
    return Response(status_code=204)
