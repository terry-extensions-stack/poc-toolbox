from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import func, select

from poc_toolbox.api.dependencies import PaginationDependency, SessionDependency
from poc_toolbox.api.errors import APIError
from poc_toolbox.api.podcast_video_contracts import PodcastVideoPage
from poc_toolbox.clients.rss import RSSConfigurationError, RSSTimeoutError, RSSUnavailableError, fetch_articles
from poc_toolbox.db_models.rss_article_snapshot import RSSArticleSnapshot
from poc_toolbox.repositories.article_snapshots import load_snapshots, save_snapshots
from poc_toolbox.repositories.podcast_videos import generated_videos

router = APIRouter(prefix='/api/podcast-videos', tags=['podcast-videos'])


def article_uuid(value: str | None) -> UUID | None:
    try:
        return UUID(value) if value else None
    except ValueError:
        return None


async def recall_articles(ids: list[UUID], session: SessionDependency) -> dict[UUID, RSSArticleSnapshot]:
    snapshots = await load_snapshots(session, ids)
    missing = [identifier for identifier in ids if identifier not in snapshots]
    if not missing:
        return snapshots
    try:
        articles = await fetch_articles(missing)
    except RSSConfigurationError:
        raise APIError(503, 'RSS_CONFIGURATION_UNAVAILABLE', 'RSS service configuration is unavailable') from None
    except RSSTimeoutError:
        raise APIError(504, 'RSS_TIMEOUT', 'RSS service timed out') from None
    except RSSUnavailableError:
        raise APIError(502, 'RSS_UNAVAILABLE', 'RSS article retrieval failed') from None
    await save_snapshots(session, articles)
    snapshots.update(await load_snapshots(session, list(articles)))
    return snapshots


@router.get('', response_model=PodcastVideoPage)
async def list_videos(session: SessionDependency, pagination: PaginationDependency) -> dict:
    """List the newest successful video per podcast, enriched with RSS article details."""
    videos = generated_videos()
    total = await session.scalar(select(func.count()).select_from(videos))
    rows = await session.execute(
        select(videos)
        .order_by(videos.c.created_at.desc().nulls_last(), videos.c.job_id.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    items = [
        {
            'id': row.id,
            'job_id': row.job_id,
            'article_id': article_uuid(row.article_id),
            'title': row.title or '',
            'image_url': row.image_url,
            'status': 'SUCCEEDED',
            'created_at': row.created_at,
            'download_url': f'/api/podcast-jobs/{row.job_id}/download',
        }
        for row in rows
    ]
    ids = list(dict.fromkeys(item['article_id'] for item in items if item['article_id'] is not None))
    articles = await recall_articles(ids, session)
    return {
        'items': [{**item, 'article': articles.get(item['article_id'])} for item in items],
        'total': total,
        'page': pagination.page,
        'page_size': pagination.page_size,
    }
