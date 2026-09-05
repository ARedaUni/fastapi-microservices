import asyncio

import jwt
from jwt import PyJWKClient

from app.core.config import settings

ALGORITHM = "RS256"

# This service's name in a token's `aud`. A token minted only for users is not
# a pass into here.
AUDIENCE = "canvas"

# Caches the key set and refetches on an unseen `kid`, which is the whole
# reason users can rotate its key without this service being redeployed.
jwks_client = PyJWKClient(settings.JWKS_URL)


async def subject_of(token: str) -> str:
    """Who the issuer says this is, or raise.

    PyJWKClient is synchronous and hits the network on a cache miss, so it goes
    to a thread -- same reason bcrypt does in users.
    """
    key = await asyncio.to_thread(jwks_client.get_signing_key_from_jwt, token)
    payload = jwt.decode(
        token,
        key=key.key,
        # Pinned, never taken from the header: the verifying key is published,
        # so trusting `alg` would accept an HS256 token signed with it.
        algorithms=[ALGORITHM],
        issuer=settings.JWT_ISSUER,
        audience=AUDIENCE,
    )
    return str(payload["sub"])
