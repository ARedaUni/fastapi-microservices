"""Authorization regression net.

These exist to catch behaviour changes during the dependency modernization.
Every assertion here documents behaviour the service has *today*.
"""
from datetime import datetime, timedelta
from typing import Dict

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.security import ALGORITHM


def _encode(payload: Dict) -> str:
    from jose import jwt

    return jwt.encode(
        payload, key=settings.SECRET_KEY.get_secret_value(), algorithm=ALGORITHM
    )


@pytest.mark.asyncio
async def test_login_with_wrong_password_is_rejected(client: AsyncClient):
    res = await client.post(
        "/api/v1/login/",
        data={"username": settings.FIRST_USER_EMAIL, "password": "not-the-password"},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Incorrect email or password"


@pytest.mark.asyncio
async def test_login_with_unknown_email_is_rejected(client: AsyncClient):
    res = await client.post(
        "/api/v1/login/",
        data={"username": "nobody@example.com", "password": "whatever"},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_protected_route_without_a_token_is_unauthorized(client: AsyncClient):
    res = await client.get("/api/v1/home/")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_with_a_malformed_token_is_forbidden(client: AsyncClient):
    res = await client.get(
        "/api/v1/home/", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_protected_route_with_an_expired_token_is_forbidden(client: AsyncClient):
    expired = _encode(
        {"exp": datetime(2020, 1, 1) + timedelta(minutes=1), "user_id": "1"}
    )
    res = await client.get(
        "/api/v1/home/", headers={"Authorization": f"Bearer {expired}"}
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_token_for_a_deleted_user_is_not_found(client: AsyncClient):
    orphan = _encode(
        {"exp": datetime.utcnow() + timedelta(minutes=5), "user_id": "999999"}
    )
    res = await client.get(
        "/api/v1/users/999999/", headers={"Authorization": f"Bearer {orphan}"}
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_home_another_is_deliberately_public(client: AsyncClient):
    """Demo surface: unlike /home/, this route carries no auth dependency."""
    res = await client.get("/api/v1/home/another/")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_listing_users_requires_a_superuser(
    client: AsyncClient, normal_user_token_headers: Dict[str, str]
):
    res = await client.get("/api/v1/users/", headers=normal_user_token_headers)
    assert res.status_code == 403
    assert res.json()["detail"] == "The user doesn't have enough privileges"


@pytest.mark.asyncio
async def test_creating_a_user_requires_a_superuser(
    client: AsyncClient, normal_user_token_headers: Dict[str, str]
):
    res = await client.post(
        "/api/v1/users/",
        json={"email": "other@example.com", "password": "pw"},
        headers=normal_user_token_headers,
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_a_normal_user_may_read_itself(
    client: AsyncClient,
    normal_user: Dict[str, str],
    normal_user_token_headers: Dict[str, str],
):
    res = await client.get(
        f"/api/v1/users/{normal_user['id']}/", headers=normal_user_token_headers
    )
    assert res.status_code == 200
    assert res.json()["email"] == normal_user["email"]


@pytest.mark.asyncio
async def test_a_normal_user_may_not_read_another_user(
    client: AsyncClient,
    normal_user_token_headers: Dict[str, str],
    superuser_token_headers: Dict[str, str],
):
    other = await client.post(
        "/api/v1/users/",
        json={"email": "third@example.com", "password": "pw"},
        headers=superuser_token_headers,
    )
    res = await client.get(
        f"/api/v1/users/{other.json()['id']}/", headers=normal_user_token_headers
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_an_inactive_user_cannot_use_a_valid_token(
    client: AsyncClient,
    normal_user: Dict[str, str],
    normal_user_token_headers: Dict[str, str],
    superuser_token_headers: Dict[str, str],
):
    deactivate = await client.put(
        f"/api/v1/users/{normal_user['id']}/",
        json={"is_active": False},
        headers=superuser_token_headers,
    )
    assert deactivate.status_code == 200, deactivate.json()
    # /home/ only decodes the token; the active check lives in get_current_user.
    res = await client.get(
        f"/api/v1/users/{normal_user['id']}/", headers=normal_user_token_headers
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Inactive user"
