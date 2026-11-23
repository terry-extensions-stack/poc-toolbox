import base64
import logging
import re
import socket

from ipaddress import ip_address, ip_network
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from pydantic import BaseModel, ConfigDict, HttpUrl

from poc_toolbox.config.podcast import PodcastSettings

logger = logging.getLogger(__name__)


def diagnostic_text(value: object, secret: str = '') -> str:
    text = str(value)
    if secret:
        text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'https?://\S+', '[URL REDACTED]', text)
    text = re.sub(r'(?i)bearer\s+\S+', 'Bearer [REDACTED]', text)
    return text[:4000]


class ProviderError(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    code: str | None = None
    message: str | None = None


class ProviderContent(BaseModel):
    video_url: HttpUrl | None = None


class ProviderTask(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    id: str
    status: str = 'queued'
    content: ProviderContent | None = None
    error: ProviderError | None = None
    request_id: str | None = None


def validate_url(url: str) -> None:
    parsed = urlsplit(url)
    host = parsed.hostname or ''
    settings = PodcastSettings()
    allowed = settings.allowed_hosts.split(',')
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Only HTTPS asset URLs without credentials are supported')
    if not any(
        host == domain.strip().lstrip('.') or host.endswith(domain.strip()) for domain in allowed if domain.strip()
    ):
        raise ValueError('Asset host is not allowed')
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    trusted = [ip_network(network) for network in settings.trusted_download_networks.split(',') if network]
    resolved = [ip_address(address[4][0]) for address in addresses]
    if not resolved or any(
        not address.is_global and not any(address in network for network in trusted) for address in resolved
    ):
        raise ValueError('Asset host must resolve to public addresses')


def download(url: str, destination: Path, maximum: int = 512 * 1024 * 1024) -> None:
    validate_url(url)
    partial = destination.with_suffix('.part')
    try:
        with httpx.stream('GET', url, timeout=120, follow_redirects=False) as response:
            response.raise_for_status()
            size = 0
            with partial.open('wb') as output:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > maximum:
                        raise ValueError('Asset exceeds size limit')
                    output.write(chunk)
            if not size:
                raise ValueError('Empty asset')
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def image_data(path: Path) -> str:
    if not path.read_bytes().startswith(b'\xff\xd8\xff'):
        raise ValueError('Expected JPEG image')
    return 'data:image/jpeg;base64,' + base64.b64encode(path.read_bytes()).decode('ascii')


class Seedance:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.url = base_url.rstrip('/') + '/contents/generations/tasks'
        self.headers = {'Authorization': f'Bearer {api_key}'}

    def submit(self, payload: dict) -> ProviderTask:
        response = httpx.post(self.url, headers=self.headers, json=payload, timeout=60)
        return self.parse_response(response)

    def poll(self, task_id: str) -> ProviderTask:
        response = httpx.get(f'{self.url}/{task_id}', headers=self.headers, timeout=60)
        return self.parse_response(response)

    def parse_response(self, response: httpx.Response) -> ProviderTask:
        secret = self.headers['Authorization'].removeprefix('Bearer ')
        request_id = diagnostic_text(
            response.headers.get('x-request-id') or response.headers.get('x-tt-logid') or '', secret
        )
        try:
            payload = response.json()
        except ValueError:
            logger.error(
                'Provider returned non-JSON response: http_status=%s request_id=%s', response.status_code, request_id
            )
            response.raise_for_status()
            raise ValueError('Provider returned non-JSON response') from None
        if not isinstance(payload, dict):
            raise ValueError('Provider response must be a JSON object')
        error = payload.get('error')
        if isinstance(error, dict):
            payload['error'] = {
                field: diagnostic_text(error[field], secret) if error.get(field) is not None else None
                for field in ('code', 'message')
            }
        elif error is not None:
            payload['error'] = {'message': diagnostic_text(error, secret)}
        payload['request_id'] = diagnostic_text(payload.get('request_id') or request_id or '', secret) or None
        if response.is_error:
            logger.error(
                'Provider HTTP failure: http_status=%s request_id=%s error=%s',
                response.status_code,
                payload['request_id'],
                payload.get('error'),
            )
        response.raise_for_status()
        return ProviderTask.model_validate(payload)
