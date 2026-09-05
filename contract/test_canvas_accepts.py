"""Terms 5-6: what `canvas` does with a token it did not sign.

What this suite cannot prove, and why: audience isolation -- that a token
minted only for `users` is refused by `canvas` -- needs a token signed by the
real private key with a narrowed `aud`, and nothing outside `users` can mint
one. From here every forgery fails on the signature first, so the audience
check is never reached. That assertion belongs in `canvas/tests`, where the
signing key is under the test's control. A contract test can pin the wire
format and the rejections an outsider can actually trigger; it cannot stand in
for a service's own enforcement matrix.
"""

import random
from typing import Any, Dict

import httpx
import jwt
from conftest import ALGORITHM, CANVAS_AUDIENCE, bearer, mint, signing_key

# canvas' grid is 100x100. Hardcoded rather than imported: importing
# `app.models.claims.GRID_SIZE` would be a dependency on the implementation,
# and a client in another language would have to hardcode it too.
GRID_SIZE = 100


def a_free_tile() -> Dict[str, Any]:
    """A tile nobody has taken yet, probably.

    ponytail: random, not reserved. Holds never expire until stage 3 builds the
    worker, so claims accumulate; at ~140 rows the birthday bound makes a
    collision likely and these tests start flaking on 409. Stage 3, or a reset
    hook on canvas, is the fix -- not a retry loop here.
    """
    return {
        "x": random.randrange(GRID_SIZE),
        "y": random.randrange(GRID_SIZE),
        "colour": "#ff8800",
    }


def issuer_of(token: str) -> str:
    """Read `iss` off a real token, so forgeries differ only in who signed them."""
    return jwt.decode(token, options={"verify_signature": False})["iss"]


def subject_of(token: str, jwks: Dict[str, Any]) -> str:
    header = jwt.get_unverified_header(token)
    return jwt.decode(
        token,
        key=signing_key(jwks, header["kid"]),
        algorithms=[ALGORITHM],
        audience=CANVAS_AUDIENCE,
    )["sub"]


def test_a_claim_without_a_token_is_unauthorized(canvas: httpx.Client) -> None:
    res = canvas.post("/api/v1/claims/", json=a_free_tile())

    assert res.status_code == 401, res.text


def test_a_token_with_an_unknown_key_id_is_unauthorized(
    canvas: httpx.Client, access_token: str, foreign_key: Any
) -> None:
    """The lookup half: a `kid` that is in no published JWKS resolves to no key."""
    forged = mint(
        foreign_key, kid="not-a-published-key", issuer=issuer_of(access_token)
    )

    res = canvas.post("/api/v1/claims/", json=a_free_tile(), headers=bearer(forged))

    assert res.status_code == 401, res.text


def test_a_token_signed_by_a_foreign_key_is_unauthorized(
    canvas: httpx.Client, access_token: str, jwks: Dict[str, Any], foreign_key: Any
) -> None:
    """The signature half, and the sharper of the two.

    This forgery borrows a *real* `kid`, so the verifier finds a key and has to
    actually check the maths. A service that only matched key ids would pass
    the test above and fail here.
    """
    forged = mint(
        foreign_key, kid=jwks["keys"][0]["kid"], issuer=issuer_of(access_token)
    )

    res = canvas.post("/api/v1/claims/", json=a_free_tile(), headers=bearer(forged))

    assert res.status_code == 401, res.text


def test_a_claim_is_owned_by_the_token_subject(
    canvas: httpx.Client, access_token: str, jwks: Dict[str, Any]
) -> None:
    """Term 6, and the end of `owner` being free text.

    canvas has no user table and never will. The subject of a token `users`
    signed is the whole of what it knows about who is drawing.
    """
    res = canvas.post(
        "/api/v1/claims/", json=a_free_tile(), headers=bearer(access_token)
    )

    assert res.status_code == 201, res.text
    assert res.json()["owner"] == subject_of(access_token, jwks)


def test_an_owner_in_the_request_body_is_not_believed(
    canvas: httpx.Client, access_token: str, jwks: Dict[str, Any]
) -> None:
    """The bug this stage closes: today anyone can claim a tile as "ada"."""
    res = canvas.post(
        "/api/v1/claims/",
        json={**a_free_tile(), "owner": "ada"},
        headers=bearer(access_token),
    )

    assert res.status_code in (201, 422), res.text
    if res.status_code == 201:
        assert res.json()["owner"] == subject_of(access_token, jwks)
