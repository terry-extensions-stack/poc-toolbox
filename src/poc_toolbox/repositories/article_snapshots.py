from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from poc_toolbox.clients.rss_contracts import RSSArticle
from poc_toolbox.db_models.rss_article_snapshot import RSSArticleSnapshot


async def load_snapshots(session: AsyncSession, ids: list[UUID]) -> dict[UUID, RSSArticleSnapshot]:
    if not ids:
        return {}
    snapshots = await session.scalars(select(RSSArticleSnapshot).where(RSSArticleSnapshot.id.in_(ids)))
    return {snapshot.id: snapshot for snapshot in snapshots}


async def save_snapshots(session: AsyncSession, articles: dict[UUID, RSSArticle]) -> None:
    if not articles:
        return
    statement = insert(RSSArticleSnapshot).values([article.model_dump() for article in articles.values()])
    await session.execute(statement.on_conflict_do_nothing(index_elements=['id']))
