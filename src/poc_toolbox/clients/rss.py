from uuid import UUID

import httpx

from pydantic import ValidationError

from poc_toolbox.clients.rss_contracts import RSSArticle, RSSArticleBatch
from poc_toolbox.config.rss import RSSSettings


class RSSConfigurationError(Exception):
    pass


class RSSUnavailableError(Exception):
    pass


class RSSTimeoutError(Exception):
    pass


async def fetch_articles(ids: list[UUID]) -> dict[UUID, RSSArticle]:
    if not ids:
        return {}
    try:
        settings = RSSSettings()
    except ValidationError:
        raise RSSConfigurationError from None
    headers = {
        'x-admin-token': settings.admin_token.get_secret_value(),
        'X-User-ID': settings.user_id.get_secret_value(),
        'X-Device-ID': settings.device_id.get_secret_value(),
        'Authorization': f'Bearer {settings.bearer_token.get_secret_value()}',
    }
    try:
        async with httpx.AsyncClient(timeout=settings.timeout_seconds, follow_redirects=False) as client:
            response = await client.post(
                f'{str(settings.base_url).rstrip("/")}/v1/articles/batch-get',
                headers=headers,
                json={'ids': [str(identifier) for identifier in ids]},
            )
            response.raise_for_status()
            batch = RSSArticleBatch.model_validate(response.json())
    except httpx.TimeoutException:
        raise RSSTimeoutError from None
    except (httpx.HTTPError, ValueError):
        raise RSSUnavailableError from None
    articles: dict[UUID, RSSArticle] = {}
    for article in batch.items:
        if article.id in articles:
            raise RSSUnavailableError
        articles[article.id] = article
    return {identifier: articles[identifier] for identifier in ids if identifier in articles}
