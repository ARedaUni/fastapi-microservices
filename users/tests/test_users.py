"""User endpoint behaviour, including the paths the upgrade must preserve."""
from typing import Dict

import pytest
from httpx import AsyncClient

from app.core.config import settings


@pytest.mark.asyncio
async def test_updating_a_user_without_a_password_keeps_the_old_one(
    client: AsyncClient,
    normal_user: Dict[str, str],
    superuser_token_headers: Dict[str, str],
):
    """A partial update must not require a password (regression: used to 500)."""
    res = await client.put(
        f"/api/v1/users/{normal_user['id']}/",
        json={"full_name": "Renamed"},
        headers=superuser_token_headers,
    )
    assert res.status_code == 200, res.json()
    assert res.json()["full_name"] == "Renamed"

    login = await client.post(
        "/api/v1/login/",
        data={"username": normal_user["email"], "password": normal_user["password"]},
    )
    assert login.status_code == 200, "the original password must still work"


@pytest.mark.asyncio
async def test_updating_a_user_with_a_password_replaces_it(
    client: AsyncClient,
    normal_user: Dict[str, str],
    superuser_token_headers: Dict[str, str],
):
    res = await client.put(
        f"/api/v1/users/{normal_user['id']}/",
        json={"password": "brand-new-password"},
        headers=superuser_token_headers,
    )
    assert res.status_code == 200, res.json()

    old = await client.post(
        "/api/v1/login/",
        data={"username": normal_user["email"], "password": normal_user["password"]},
    )
    assert old.status_code == 400
    new = await client.post(
        "/api/v1/login/",
        data={"username": normal_user["email"], "password": "brand-new-password"},
    )
    assert new.status_code == 200


@pytest.mark.asyncio
async def test_updating_a_missing_user_is_not_found(
    client: AsyncClient, superuser_token_headers: Dict[str, str]
):
    res = await client.put(
        "/api/v1/users/999999/",
        json={"full_name": "Ghost"},
        headers=superuser_token_headers,
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_creating_a_duplicate_email_is_a_conflict(
    client: AsyncClient,
    normal_user: Dict[str, str],
    superuser_token_headers: Dict[str, str],
):
    res = await client.post(
        "/api/v1/users/",
        json={"email": normal_user["email"], "password": "pw"},
        headers=superuser_token_headers,
    )
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_a_superuser_cannot_delete_itself(
    client: AsyncClient, superuser_token_headers: Dict[str, str]
):
    me = await client.post(
        "/api/v1/login/",
        data={
            "username": settings.FIRST_USER_EMAIL,
            "password": settings.FIRST_USER_PASSWORD.get_secret_value(),
        },
    )
    assert me.status_code == 200
    users = await client.get("/api/v1/users/", headers=superuser_token_headers)
    my_id = next(
        u["id"] for u in users.json() if u["email"] == settings.FIRST_USER_EMAIL
    )
    res = await client.delete(
        f"/api/v1/users/{my_id}/", headers=superuser_token_headers
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "User can't delete itself"


@pytest.mark.asyncio
async def test_deleting_a_user(
    client: AsyncClient,
    normal_user: Dict[str, str],
    superuser_token_headers: Dict[str, str],
):
    res = await client.delete(
        f"/api/v1/users/{normal_user['id']}/", headers=superuser_token_headers
    )
    assert res.status_code == 204
    gone = await client.get(
        f"/api/v1/users/{normal_user['id']}/", headers=superuser_token_headers
    )
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_deleting_a_missing_user_is_not_found(
    client: AsyncClient, superuser_token_headers: Dict[str, str]
):
    res = await client.delete("/api/v1/users/999999/", headers=superuser_token_headers)
    assert res.status_code == 404
