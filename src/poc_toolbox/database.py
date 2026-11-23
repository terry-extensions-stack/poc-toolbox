from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from poc_toolbox.config import DatabaseSettings


@asynccontextmanager
async def database_lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = DatabaseSettings()
    engine = create_async_engine(settings.database_url.get_secret_value(), hide_parameters=True, pool_pre_ping=True)
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield
    finally:
        await engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session, session.begin():
        yield session
