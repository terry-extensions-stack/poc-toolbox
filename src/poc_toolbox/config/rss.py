from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class RSSSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='RSS_', hide_input_in_errors=True)
    base_url: HttpUrl
    admin_token: SecretStr = Field(min_length=1)
    user_id: SecretStr = Field(min_length=1)
    device_id: SecretStr = Field(min_length=1)
    bearer_token: SecretStr = Field(min_length=1)
    timeout_seconds: float = Field(default=10, gt=0, allow_inf_nan=False)
