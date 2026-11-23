from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class PodcastSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='PODCAST_', hide_input_in_errors=True)
    broker_url: str = 'redis://redis:6379/0'
    work_dir: Path = Path('/tmp/podcasts')
    subtitle_font: Path = Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    allowed_hosts: str = '.myqcloud.com,.volces.com,.volccdn.com,.byteimg.com,.ibytedtos.com'
    trusted_download_networks: list[str] = Field(default_factory=list)


class StorageSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='COS_', hide_input_in_errors=True)
    region: str
    bucket: str
    secret_id: SecretStr
    secret_key: SecretStr
    prefix: str = 'podcasts'


class SeedanceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='SEEDANCE_', hide_input_in_errors=True)
    base_url: str = 'https://ark.cn-beijing.volces.com/api/v3'
    model_id: str = Field(default='doubao-seedance-1-0-pro-fast-251015', min_length=1)
    api_key: SecretStr = Field(min_length=1)
