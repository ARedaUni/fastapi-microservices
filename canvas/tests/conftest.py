import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.api.deps import get_session
from app.core.database import SessionLocal, engine
from app.main import app
from app.models.claims import Claim


@pytest.fixture()
async def connection():
    async with engine.begin() as conn:
        yield conn
        await conn.rollback()


@pytest.fixture()
async def session(connection: AsyncConnection):
    # Bound to a connection that already has a transaction, so the session's
    # own commits become savepoints and the rollback above still undoes them.
    async with AsyncSession(connection, expire_on_commit=False) as _session:
        yield _session


@pytest.fixture(autouse=True)
async def override_dependency(session: AsyncSession):
    app.dependency_overrides[get_session] = lambda: session


@pytest.fixture()
async def client():
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as ac,
        LifespanManager(app),
    ):
        yield ac


@pytest.fixture()
async def racing_sessions(override_dependency):
    """Undo the shared-session override, so two requests can genuinely contend.

    Every other test runs inside one transaction that is rolled back, which is
    fast and isolated but makes concurrency untestable: two requests sharing a
    session are serialised by the session, and the unique index is never asked
    anything. This hands each request its own connection -- real commits, real
    lock waits -- and cleans up by deleting rows afterwards.

    Depends on override_dependency purely for ordering: the autouse fixture has
    to install the shared session before this replaces it.
    """

    async def independent_session():
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = independent_session
    yield
    async with SessionLocal() as session:
        await session.execute(delete(Claim))
        await session.commit()
