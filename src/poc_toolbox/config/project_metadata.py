import tomllib

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ProjectMetadata(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    name: str = Field(min_length=1, pattern=r'\S')
    version: str = Field(min_length=1, pattern=r'\S')
    description: str = Field(min_length=1, pattern=r'\S')


def load_project_metadata(module_path: Path) -> ProjectMetadata:
    project_file = next(
        (
            directory / 'pyproject.toml'
            for directory in module_path.resolve().parents
            if (directory / 'pyproject.toml').is_file()
        ),
        None,
    )
    if project_file is None:
        raise FileNotFoundError(f'pyproject.toml not found above {module_path}')
    with project_file.open('rb') as source:
        project = tomllib.load(source).get('project', {})
    return ProjectMetadata.model_validate(project)
