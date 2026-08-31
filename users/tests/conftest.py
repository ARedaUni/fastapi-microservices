from typing import Dict

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.api.deps import get_session
from app.core.config import settings
from app.core.database import engine
from app.main import app


@pytest.fixture()
async def connection():
    async with engine.begin() as conn:
        yield conn
        await conn.rollback()


@pytest.fixture()
async def session(connection: AsyncConnection):
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
async def superuser_token_headers(client: AsyncClient) -> Dict[str, str]:
    login_data = {
        "username": settings.FIRST_USER_EMAIL,
        "password": settings.FIRST_USER_PASSWORD.get_secret_value(),
    }
    res = await client.post("/api/v1/login/", data=login_data)
    access_token = res.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture()
async def normal_user(
    client: AsyncClient, superuser_token_headers: Dict[str, str]
) -> Dict[str, str]:
    """A non-superuser, created through the API so the password hash is real."""
    credentials = {"email": "normal@example.com", "password": "normal-password"}
    res = await client.post(
        "/api/v1/users/", json=credentials, headers=superuser_token_headers
    )
    assert res.status_code == 200, res.json()
    return {**credentials, "id": res.json()["id"]}


@pytest.fixture()
async def normal_user_token_headers(
    client: AsyncClient, normal_user: Dict[str, str]
) -> Dict[str, str]:
    res = await client.post(
        "/api/v1/login/",
        data={"username": normal_user["email"], "password": normal_user["password"]},
    )
    assert res.status_code == 200, res.json()
    return {"Authorization": f"Bearer {res.json()['access_token']}"}
