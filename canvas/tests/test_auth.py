from datetime import timedelta

from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient

from tests.conftest import auth

CLAIMS = "/api/v1/claims/"
TILE = {"x": 4, "y": 7, "colour": "#ff0055"}


async def test_a_claim_without_a_token_is_unauthorized(anonymous: AsyncClient):
    assert (await anonymous.post(CLAIMS, json=TILE)).status_code == 401


async def test_a_claim_with_a_malformed_token_is_unauthorized(client: AsyncClient):
    res = await client.post(
        CLAIMS, json=TILE, headers={"Authorization": "Bearer not-a-jwt"}
    )

    assert res.status_code == 401


async def test_a_token_signed_by_an_unpublished_key_is_unauthorized(
    client: AsyncClient,
):
    """Borrows the published `kid`, so the key resolves and the signature is
    what fails. Matching key ids alone would pass this.
    """
    foreign = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    res = await client.post(CLAIMS, json=TILE, headers=auth(key=foreign))

    assert res.status_code == 401


async def test_a_token_with_an_unknown_key_id_is_unauthorized(client: AsyncClient):
    res = await client.post(CLAIMS, json=TILE, headers=auth(kid="never-published"))

    assert res.status_code == 401


async def test_a_token_minted_only_for_users_is_unauthorized(client: AsyncClient):
    """Audience isolation. Without it, handing users your token would let users
    take tiles as you.
    """
    res = await client.post(CLAIMS, json=TILE, headers=auth(aud=["users"]))

    assert res.status_code == 401


async def test_a_token_from_another_issuer_is_unauthorized(client: AsyncClient):
    res = await client.post(CLAIMS, json=TILE, headers=auth(iss="http://not-users"))

    assert res.status_code == 401


async def test_an_expired_token_is_unauthorized(client: AsyncClient):
    res = await client.post(
        CLAIMS, json=TILE, headers=auth(expires_in=timedelta(minutes=-1))
    )

    assert res.status_code == 401


async def test_a_claim_is_owned_by_the_token_subject(client: AsyncClient):
    res = await client.post(CLAIMS, json=TILE, headers=auth(sub="42"))

    assert res.status_code == 201, res.json()
    assert res.json()["owner"] == "42"


async def test_an_owner_in_the_request_body_is_ignored(client: AsyncClient):
    """The bug this stage closes: `owner` used to be whatever you typed."""
    res = await client.post(
        CLAIMS, json={**TILE, "owner": "ada"}, headers=auth(sub="42")
    )

    assert res.status_code == 201, res.json()
    assert res.json()["owner"] == "42"


async def test_listing_the_canvas_needs_no_token(anonymous: AsyncClient):
    """Deliberate: the canvas is the public artefact. Drawing needs identity,
    looking does not.
    """
    assert (await anonymous.get(CLAIMS)).status_code == 200
