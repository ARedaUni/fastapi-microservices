"""Cross-service contract tests: the wire, not the code.

Nothing in this directory imports `app`. These tests know only what a third
party could learn from outside -- two base URLs, a login form, a JWKS document
and RFC 7519 -- so they survive either service being rewritten and fail the
moment the agreement between them moves.

That boundary is the point. `users/tests` and `canvas/tests` each prove their
own service does the right thing with a key they control; only this suite
proves the two agree about what a token *is*. It is the gap
`docs/second-service.md` calls "no contract tests".

Run against a live stack: `make contract`.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

# Compose service names: this suite runs inside the `api` container, where
# `api` is users and `canvas-api` is canvas. Overridable so the same tests can
# be pointed at a cluster, or at localhost from outside compose.
USERS_URL = os.environ.get("CONTRACT_USERS_URL", "http://api")
CANVAS_URL = os.environ.get("CONTRACT_CANVAS_URL", "http://canvas-api")

# The seeded superuser. Read from the environment rather than app.core.config,
# because importing either service's settings would be a dependency on its
# implementation -- the thing this directory exists not to have.
EMAIL = os.environ["FIRST_USER_EMAIL"]
PASSWORD = os.environ["FIRST_USER_PASSWORD"]

# Term 4 of the agreement: the names a token is minted for. Each service pins
# its own, so a token issued for one is inert at the other.
USERS_AUDIENCE = "users"
CANVAS_AUDIENCE = "canvas"

JWKS_PATH = "/.well-known/jwks.json"

# Pinned, never read from the token header. A verifier that trusts the header's
# `alg` can be handed an HS256 token signed with the published public key as
# the HMAC secret, and will happily agree it is valid.
ALGORITHM = "RS256"

# RFC 7517 private members. A JWKS is served to anyone who asks; if one of
# these ever appears in it, the signing key has been published.
PRIVATE_JWK_MEMBERS = {"d", "p", "q", "dp", "dq", "qi", "oth"}


@pytest.fixture(scope="session")
def users():
    with httpx.Client(base_url=USERS_URL, timeout=10) as client:
        yield client


@pytest.fixture(scope="session")
def canvas():
    with httpx.Client(base_url=CANVAS_URL, timeout=10) as client:
        yield client


@pytest.fixture(scope="session")
def access_token(users: httpx.Client) -> str:
    """A token, obtained the only way a client can: by logging in."""
    res = users.post("/api/v1/login/", data={"username": EMAIL, "password": PASSWORD})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


@pytest.fixture(scope="session")
def jwks(users: httpx.Client) -> Dict[str, Any]:
    res = users.get(JWKS_PATH)
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture(scope="session")
def foreign_key() -> rsa.RSAPrivateKey:
    """A key nobody published: the stand-in for an attacker's key.

    Session-scoped because 2048-bit RSA keygen is slow enough to notice, and
    every test that needs one needs the same thing from it.
    """
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def signing_key(jwks: Dict[str, Any], kid: str):
    """The published key with this id, as a verifier would find it.

    Deliberately spelled out rather than handed to PyJWKClient: the lookup by
    `kid` *is* half the contract, and a helper that hides it would leave the
    other half of rotation untested.
    """
    for key in jwks["keys"]:
        if key.get("kid") == kid:
            return jwt.PyJWK.from_dict(key).key
    raise AssertionError(f"no published key with kid {kid!r}")


def mint(
    private_key: rsa.RSAPrivateKey,
    *,
    kid: str,
    issuer: str,
    audience: Any = CANVAS_AUDIENCE,
    subject: str = "1",
    expires_in: timedelta = timedelta(minutes=10),
) -> str:
    """Forge a token that is well-formed in every way except who signed it."""
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "iss": issuer,
            "sub": subject,
            "aud": audience,
            "iat": now,
            "exp": now + expires_in,
        },
        key=private_key,
        algorithm=ALGORITHM,
        headers={"kid": kid},
    )


def bearer(token: Optional[str]) -> Dict[str, str]:
    return {} if token is None else {"Authorization": f"Bearer {token}"}
