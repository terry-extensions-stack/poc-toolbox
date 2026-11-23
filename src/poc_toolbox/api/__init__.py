from poc_toolbox.api.ai_templates import router as template_router
from poc_toolbox.api.errors import register_error_handlers
from poc_toolbox.api.model_configs import router as model_config_router
from poc_toolbox.api.podcasts import router as podcast_router
from poc_toolbox.api.service_metadata import router as metadata_router

__all__ = ['metadata_router', 'model_config_router', 'podcast_router', 'register_error_handlers', 'template_router']
