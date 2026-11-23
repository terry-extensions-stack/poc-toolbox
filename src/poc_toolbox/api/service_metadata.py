from fastapi import APIRouter, Request

from poc_toolbox.config.project_metadata import ProjectMetadata

router = APIRouter(tags=['service'])


class ServiceMetadata(ProjectMetadata):
    docs_url: str | None
    redoc_url: str | None
    openapi_url: str | None


@router.get('/', response_model=ServiceMetadata)
async def get_service_metadata(request: Request) -> ServiceMetadata:
    return ServiceMetadata(
        **request.app.state.project_metadata.model_dump(),
        docs_url=request.app.docs_url,
        redoc_url=request.app.redoc_url,
        openapi_url=request.app.openapi_url,
    )
