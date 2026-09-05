from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient

from app.core.config import settings
from app.core.security import ALGORITHM, AUDIENCES, PRIVATE_KEY, PUBLIC_JWK

PRIVATE_JWK_MEMBERS = {"d", "p", "q", "dp", "dq", "qi", "oth"}


def _claims(**overrides):
    now = datetime.now(timezone.utc)
    return {
        "iss": settings.JWT_ISSUER,
        "sub": "1",
        "aud": AUDIENCES,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        **overrides,
    }


@pytest.mark.asyncio
async def test_the_jwks_publishes_the_signing_key(client: AsyncClient):
    res = await client.get("/.well-known/jwks.json")

    assert res.status_code == 200
    assert res.json()["keys"] == [PUBLIC_JWK]


@pytest.mark.asyncio
async def test_the_jwks_never_exposes_private_key_material(client: AsyncClient):
    for key in (await client.get("/.well-known/jwks.json")).json()["keys"]:
        assert not PRIVATE_JWK_MEMBERS & key.keys()


@pytest.mark.asyncio
async def test_a_token_signed_by_an_unpublished_key_is_rejected(client: AsyncClient):
    """Borrows the real `kid`, so the key is found and the signature is what
    fails -- a service that only matched key ids would pass this otherwise.
    """
    foreign = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        _claims(), key=foreign, algorithm=ALGORITHM, headers={"kid": PUBLIC_JWK["kid"]}
    )

    res = await client.get(
        "/api/v1/home/", headers={"Authorization": f"Bearer {forged}"}
    )

    assert res.status_code == 403


@pytest.mark.asyncio
async def test_a_token_minted_only_for_canvas_is_rejected(client: AsyncClient):
    """Audience isolation, and the reason `aud` is not decoration: without it,
    handing canvas your token would let canvas act as you here.

    Only provable where the signing key is available -- the cross-service
    contract suite cannot mint this.
    """
    elsewhere = jwt.encode(
        _claims(aud=["canvas"]),
        key=PRIVATE_KEY,
        algorithm=ALGORITHM,
        headers={"kid": PUBLIC_JWK["kid"]},
    )

    res = await client.get(
        "/api/v1/home/", headers={"Authorization": f"Bearer {elsewhere}"}
    )

    assert res.status_code == 403


@pytest.mark.asyncio
async def test_a_token_from_another_issuer_is_rejected(client: AsyncClient):
    impostor = jwt.encode(
        _claims(iss="http://not-users"),
        key=PRIVATE_KEY,
        algorithm=ALGORITHM,
        headers={"kid": PUBLIC_JWK["kid"]},
    )

    res = await client.get(
        "/api/v1/home/", headers={"Authorization": f"Bearer {impostor}"}
    )

    assert res.status_code == 403
