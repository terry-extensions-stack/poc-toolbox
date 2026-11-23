from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(hide_input_in_errors=True, env_file=None)

    database_url: SecretStr

    @field_validator('database_url')
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
        except (ArgumentError, ValueError):
            raise ValueError('DATABASE_URL must be a valid PostgreSQL URL') from None
        if url.drivername != 'postgresql+asyncpg' or not url.database:
            raise ValueError('DATABASE_URL must identify a PostgreSQL database using asyncpg')
        return value
