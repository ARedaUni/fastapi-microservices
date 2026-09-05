"""Terms 1-4: what `users` puts on the wire.

Every assertion here is something a verifier written by someone else, in
another language, would have to rely on.
"""

from typing import Any, Dict

import httpx
import jwt
from conftest import (
    ALGORITHM,
    CANVAS_AUDIENCE,
    EMAIL,
    JWKS_PATH,
    PASSWORD,
    PRIVATE_JWK_MEMBERS,
    USERS_AUDIENCE,
    signing_key,
)


def test_login_issues_a_bearer_token(users: httpx.Client) -> None:
    res = users.post("/api/v1/login/", data={"username": EMAIL, "password": PASSWORD})

    assert res.status_code == 200, res.text
    assert res.json()["token_type"] == "bearer"
    assert res.json()["access_token"]


def test_the_jwks_is_public(users: httpx.Client) -> None:
    """No credentials. A public key is not a secret, and a verifier that had to
    authenticate to fetch one would need a credential to check a credential.
    """
    res = users.get(JWKS_PATH)

    assert res.status_code == 200, res.text
    assert res.json()["keys"], "a signer with no published keys cannot be verified"


def test_the_jwks_publishes_an_rs256_signing_key(jwks: Dict[str, Any]) -> None:
    key = jwks["keys"][0]

    assert key["kty"] == "RSA"
    assert key["alg"] == ALGORITHM
    assert key["use"] == "sig"
    assert key["kid"], "without a key id a verifier cannot tell two keys apart"


def test_the_jwks_never_exposes_private_key_material(jwks: Dict[str, Any]) -> None:
    """The failure that turns asymmetric signing back into shared-secret signing.

    Serialising the private key instead of the public one publishes `d`, `p`
    and `q` to anyone who curls the endpoint, and every reader becomes a signer.
    """
    for key in jwks["keys"]:
        assert not PRIVATE_JWK_MEMBERS & key.keys(), f"private material in {key['kid']}"


def test_the_access_token_is_signed_by_a_published_key(
    access_token: str, jwks: Dict[str, Any]
) -> None:
    """Term 3, and the whole reason the JWKS exists.

    The header names a key; the key verifies the signature. Nothing is shared
    between the two services except this document.
    """
    header = jwt.get_unverified_header(access_token)
    assert header["alg"] == ALGORITHM

    # No `issuer=`, so `iss` is read but not pinned -- the next test is the one
    # that has an opinion about its value.
    payload = jwt.decode(
        access_token,
        key=signing_key(jwks, header["kid"]),
        algorithms=[ALGORITHM],
        audience=CANVAS_AUDIENCE,
    )

    assert payload["sub"]


def test_the_access_token_names_its_issuer_and_its_audiences(
    access_token: str, jwks: Dict[str, Any]
) -> None:
    """Term 4. `iss` says who signed; `aud` says who may accept.

    Without `aud`, a token handed to one service can be replayed by that
    service against another, as the user -- the confused deputy. Each service
    checks its own name is in this list.
    """
    header = jwt.get_unverified_header(access_token)
    payload = jwt.decode(
        access_token,
        key=signing_key(jwks, header["kid"]),
        algorithms=[ALGORITHM],
        audience=CANVAS_AUDIENCE,
    )

    assert payload["iss"], "a token that does not say who signed it cannot be pinned"
    assert USERS_AUDIENCE in payload["aud"]
    assert CANVAS_AUDIENCE in payload["aud"]
    assert payload["exp"] > payload["iat"], "expiry is the only revocation there is"
