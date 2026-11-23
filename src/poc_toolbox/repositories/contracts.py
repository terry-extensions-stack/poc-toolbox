from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, StringConstraints, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ModelId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Prompt = Annotated[str, StringConstraints(min_length=1, pattern=r'\S')]
MAX_PAGE_SIZE = 100


class WriteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)

    @model_validator(mode='after')
    def reject_explicit_null(self) -> Self:
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError('Explicit null values are not allowed')
        return self


class CreateModelConfig(WriteRequest):
    name: Name
    base_url: HttpUrl = Field(max_length=2048)
    model_id: ModelId
    api_key: SecretStr = Field(min_length=1)


class UpdateModelConfig(WriteRequest):
    name: Name | None = None
    base_url: HttpUrl | None = Field(default=None, max_length=2048)
    model_id: ModelId | None = None
    api_key: SecretStr | None = Field(default=None, min_length=1)


class CreateTemplate(WriteRequest):
    name: Name
    system_prompt: str = ''
    user_prompt: Prompt
    model_config_id: UUID


class UpdateTemplate(WriteRequest):
    name: Name | None = None
    system_prompt: str | None = None
    user_prompt: Prompt | None = None
    model_config_id: UUID | None = None


class RecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime
    updated_at: datetime


class ModelConfigResponse(RecordResponse):
    base_url: str
    model_id: str
    has_api_key: bool = True


class TemplateResponse(RecordResponse):
    system_prompt: str
    user_prompt: str
    model_config_id: UUID


class PageResponse[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class Pagination:
    page: int = 1
    page_size: int = 20

    def __post_init__(self) -> None:
        if self.page < 1 or not 1 <= self.page_size <= MAX_PAGE_SIZE:
            raise ValueError('Invalid pagination')

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class EncryptionConfigurationError(Exception):
    pass
