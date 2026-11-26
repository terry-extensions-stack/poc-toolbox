from pathlib import Path

from fastapi import FastAPI

from poc_toolbox.api.ai_templates import router as template_router
from poc_toolbox.api.errors import register_error_handlers
from poc_toolbox.api.model_configs import router as model_config_router
from poc_toolbox.api.podcasts import router as podcast_router
from poc_toolbox.api.service_metadata import router as metadata_router
from poc_toolbox.config.project_metadata import load_project_metadata
from poc_toolbox.database import database_lifespan

project_metadata = load_project_metadata(Path(__file__))
app = FastAPI(title='POC Toolbox', version=project_metadata.version, lifespan=database_lifespan)
app.state.project_metadata = project_metadata
app.include_router(metadata_router)
app.include_router(model_config_router)
app.include_router(template_router)
app.include_router(podcast_router)
register_error_handlers(app)
