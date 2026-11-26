import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from poc_toolbox.config import DatabaseSettings
from poc_toolbox.db_models import BaseModel
from poc_toolbox.db_models.podcast import PodcastJob  # noqa: F401
from poc_toolbox.db_models.podcast_render import PodcastRender  # noqa: F401
from poc_toolbox.db_models.rss_article_snapshot import RSSArticleSnapshot  # noqa: F401

target_metadata = BaseModel.metadata


def run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    settings = DatabaseSettings()
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=pool.NullPool, hide_parameters=True
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


def run_offline() -> None:
    settings = DatabaseSettings()
    context.configure(
        url=settings.database_url.get_secret_value(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    supplied_connection = context.config.attributes.get('connection')
    if supplied_connection is not None:
        run_migrations(supplied_connection)
    else:
        asyncio.run(run_online())
