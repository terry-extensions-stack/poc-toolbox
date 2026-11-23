from pathlib import Path

from fastapi import FastAPI

from poc_toolbox.api import (
    metadata_router,
    model_config_router,
    podcast_router,
    register_error_handlers,
    template_router,
)
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
