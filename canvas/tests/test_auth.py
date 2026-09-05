import time
from datetime import timedelta
from typing import List

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient
from jwt.exceptions import PyJWKClientConnectionError

from app.core import security
from tests.conftest import JWKS, auth

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


async def test_a_repeated_unknown_key_id_costs_one_fetch(
    client: AsyncClient, jwks_fetches: List[int]
):
    """An unknown `kid` forces PyJWKClient to refetch the whole key set, and the
    `kid` is read from the unverified header -- so without a negative cache any
    anonymous caller turns one request here into one request to the issuer.
    """
    assert (
        await client.post(CLAIMS, json=TILE, headers=auth(kid="unheard-of"))
    ).status_code == 401
    after_first = len(jwks_fetches)

    for _ in range(3):
        assert (
            await client.post(CLAIMS, json=TILE, headers=auth(kid="unheard-of"))
        ).status_code == 401

    assert len(jwks_fetches) == after_first, "a kid already proven absent was refetched"


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


async def test_an_unreachable_issuer_is_503_and_is_not_remembered(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """503, not 401: we cannot say whether the token is good, and 401 would send
    the caller to log in again -- which also fails.

    The second half is the sharper one. An outage must not be recorded as "this
    kid does not exist", or a blip becomes a minute of confident 401s for keys
    that were fine all along. monkeypatch here, unlike the counting seam in
    conftest, because this test needs the fetch to *fail*.
    """

    def unreachable() -> None:
        raise PyJWKClientConnectionError("users is down")

    monkeypatch.setattr(security.jwks_client, "fetch_data", unreachable)

    assert (await client.post(CLAIMS, json=TILE)).status_code == 503
    assert security._unknown_kids == {}, "an outage was remembered as a bad kid"

    monkeypatch.setattr(security.jwks_client, "fetch_data", lambda: JWKS)

    assert (await client.post(CLAIMS, json=TILE)).status_code == 201


async def test_absent_kid_memory_is_bounded(client: AsyncClient):
    """The negative cache is keyed by attacker-supplied `kid`, so it needs a
    ceiling or forged tokens grow it without limit.
    """
    security._unknown_kids.update(
        {f"kid-{i}": time.monotonic() for i in range(security.MAX_UNKNOWN_KIDS)}
    )

    res = await client.post(CLAIMS, json=TILE, headers=auth(kid="one-too-many"))

    assert res.status_code == 401
    assert len(security._unknown_kids) <= security.MAX_UNKNOWN_KIDS
