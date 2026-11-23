from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AIEncryptionSettings(BaseSettings):
    model_config = SettingsConfigDict(hide_input_in_errors=True, env_file=None)

    encryption_key: SecretStr = Field(validation_alias='AI_CONFIG_ENCRYPTION_KEY')
