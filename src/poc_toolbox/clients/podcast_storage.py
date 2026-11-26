from pathlib import Path

from qcloud_cos import CosConfig, CosS3Client

from poc_toolbox.config.podcast import StorageSettings


def client() -> tuple[CosS3Client, StorageSettings]:
    settings = StorageSettings()
    config = CosConfig(
        Region=settings.region,
        SecretId=settings.secret_id.get_secret_value(),
        SecretKey=settings.secret_key.get_secret_value(),
        Scheme='https',
    )
    return CosS3Client(config), settings


def upload(path: Path, key: str) -> str:
    connection, settings = client()
    full_key = f'{settings.prefix.strip("/")}/{key}'
    connection.upload_file(Bucket=settings.bucket, Key=full_key, LocalFilePath=str(path))
    return full_key


def signed_download(key: str) -> str:
    connection, settings = client()
    return connection.get_presigned_download_url(Bucket=settings.bucket, Key=key, Expired=900)


def download_video(key: str, destination: Path) -> None:
    connection, settings = client()
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix('.part')
    connection.download_file(Bucket=settings.bucket, Key=key, DestFilePath=str(partial))
    partial.replace(destination)


def delete_video(key: str) -> None:
    connection, settings = client()
    connection.delete_object(Bucket=settings.bucket, Key=key)
