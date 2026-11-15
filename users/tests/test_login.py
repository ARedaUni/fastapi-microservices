import jwt
import pytest
from httpx import AsyncClient

from app.core.config import settings


@pytest.mark.asyncio()
async def test_login(client: AsyncClient):
    login_data = {
        "username": settings.FIRST_USER_EMAIL,
        "password": settings.FIRST_USER_PASSWORD.get_secret_value(),
    }
    res = await client.post("/api/v1/login/", data=login_data)
    assert res.status_code == 200, res.json()
    assert res.json().get("token_type") == "bearer"
    assert "access_token" in res.json().keys()


def _credentials() -> dict:
    return {
        "username": settings.FIRST_USER_EMAIL,
        "password": settings.FIRST_USER_PASSWORD.get_secret_value(),
    }


def _audience_of(token: str):
    # Unverified on purpose: test_jwks.py owns the signature; this is about aud.
    return jwt.decode(token, options={"verify_signature": False})["aud"]


@pytest.mark.asyncio
async def test_a_token_is_for_users_alone_unless_another_audience_is_asked_for(
    client: AsyncClient,
):
    res = await client.post("/api/v1/login/", data=_credentials())

    assert _audience_of(res.json()["access_token"]) == "users"


@pytest.mark.asyncio
async def test_a_client_can_ask_for_a_token_good_at_one_other_service_only(
    client: AsyncClient,
):
    """users names no other service: the client says where the token is going,
    and the token is then inert everywhere else -- including here.
    """
    res = await client.post(
        "/api/v1/login/", data={**_credentials(), "audience": "canvas"}
    )
    token = res.json()["access_token"]

    assert _audience_of(token) == "canvas"
    me = await client.get(
        "/api/v1/users/1/", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("audience", ["Canvas", "canvas users", "-canvas"])
async def test_an_audience_that_is_not_a_service_name_is_rejected(
    client: AsyncClient, audience: str
):
    res = await client.post(
        "/api/v1/login/", data={**_credentials(), "audience": audience}
    )

    assert res.status_code == 422


@pytest.mark.asyncio
async def test_an_empty_audience_is_the_same_as_none(client: AsyncClient):
    # FastAPI reads an empty form field as absent, so this falls to the default.
    res = await client.post("/api/v1/login/", data={**_credentials(), "audience": ""})

    assert _audience_of(res.json()["access_token"]) == "users"
