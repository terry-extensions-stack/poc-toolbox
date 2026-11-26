from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from poc_toolbox.api.errors import APIError
from poc_toolbox.api.podcast_preview_contracts import LayoutPreview, PreviewLayout
from poc_toolbox.services.podcast_typography import preview_layout

router = APIRouter()


@router.post('/layout-preview', response_model=LayoutPreview)
async def layout_preview(request: PreviewLayout) -> LayoutPreview:
    try:
        return await run_in_threadpool(preview_layout, request)
    except OSError:
        raise APIError(503, 'LAYOUT_FONT_UNAVAILABLE', 'Shared layout font is unavailable') from None
    except ValueError as error:
        raise APIError(422, 'LAYOUT_INVALID', str(error)) from None
