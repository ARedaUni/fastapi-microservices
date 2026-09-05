from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt
import pytest
from asgi_lifespan import LifespanManager
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.api.deps import get_session
from app.core import security
from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.main import app
from app.models.claims import Claim

# A key users never signed anything with, standing in for the one it did.
# canvas cannot tell the difference, which is the property being relied on.
SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
KID = "test-signing-key"
JWKS = {
    "keys": [
        {
            **RSAAlgorithm.to_jwk(SIGNING_KEY.public_key(), as_dict=True),
            "kid": KID,
            "use": "sig",
            "alg": "RS256",
        }
    ]
}


def mint(
    *,
    sub: str = "1",
    key: Any = SIGNING_KEY,
    kid: str = KID,
    aud: Any = None,
    iss: str = "",
    expires_in: timedelta = timedelta(minutes=10),
) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "iss": iss or settings.JWT_ISSUER,
            "sub": sub,
            "aud": aud or ["users", "canvas"],
            "iat": now,
            "exp": now + expires_in,
        },
        key=key,
        algorithm="RS256",
        headers={"kid": kid},
    )


def auth(**kwargs: Any) -> Dict[str, str]:
    return {"Authorization": f"Bearer {mint(**kwargs)}"}


@pytest.fixture(autouse=True)
def published_keys(monkeypatch: pytest.MonkeyPatch):
    """Stand in for users' JWKS endpoint.

    The seam is the network fetch and nothing else, so kid lookup, signature,
    iss, aud and exp all still run for real.
    """
    monkeypatch.setattr(security.jwks_client, "fetch_data", lambda: JWKS)


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
    """Authenticated by default -- every claim route now requires a token."""
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test", headers=auth()) as ac,
        LifespanManager(app),
    ):
        yield ac


@pytest.fixture()
async def anonymous():
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
    await _truncate_claims()  # `make contract` writes real rows to this database
    yield
    await _truncate_claims()


async def _truncate_claims() -> None:
    async with SessionLocal() as session:
        await session.execute(delete(Claim))
        await session.commit()
