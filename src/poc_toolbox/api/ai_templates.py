from uuid import UUID

from fastapi import APIRouter, Response

from poc_toolbox.api.dependencies import PaginationDependency, TemplateRepositoryDependency
from poc_toolbox.api.errors import APIError
from poc_toolbox.db_models import AITemplate
from poc_toolbox.repositories import CreateTemplate, PageResponse, TemplateResponse, UpdateTemplate

router = APIRouter(prefix='/api/ai-templates', tags=['ai-templates'])


@router.post('', response_model=TemplateResponse, status_code=201)
async def create_template(request: CreateTemplate, repository: TemplateRepositoryDependency) -> AITemplate:
    return await repository.create(request)


@router.get('', response_model=PageResponse[TemplateResponse])
async def list_templates(
    repository: TemplateRepositoryDependency,
    pagination: PaginationDependency,
    model_config_id: UUID | None = None,
) -> PageResponse[TemplateResponse]:
    records, total = await repository.list(pagination, model_config_id)
    return PageResponse(
        items=[TemplateResponse.model_validate(record) for record in records],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get('/{template_id}', response_model=TemplateResponse)
async def get_template(template_id: UUID, repository: TemplateRepositoryDependency) -> AITemplate:
    template = await repository.find_by_id(template_id)
    if template is None:
        raise APIError(404, 'NOT_FOUND', 'Template not found')
    return template


@router.patch('/{template_id}', response_model=TemplateResponse)
async def update_template(
    template_id: UUID, request: UpdateTemplate, repository: TemplateRepositoryDependency
) -> AITemplate:
    template = await repository.update(template_id, request)
    if template is None:
        raise APIError(404, 'NOT_FOUND', 'Template not found')
    return template


@router.delete('/{template_id}', status_code=204)
async def delete_template(template_id: UUID, repository: TemplateRepositoryDependency) -> Response:
    await repository.delete(template_id)
    return Response(status_code=204)
