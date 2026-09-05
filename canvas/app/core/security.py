import asyncio
import time
from typing import Dict

import jwt
from jwt import PyJWK, PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

from app.core.config import settings

ALGORITHM = "RS256"

# This service's name in a token's `aud`. A token minted only for users is not
# a pass into here.
AUDIENCE = "canvas"

# The issuer is a sibling service, so a fetch that has not finished in a couple
# of seconds is not going to. PyJWT's default is 30, which is long enough for a
# blackholed `users` to pin a thread per request until the pool is gone.
JWKS_TIMEOUT_SECONDS = 2

# How long a `kid` stays known-absent. This is rotation lag: a key published
# after we rejected its `kid` is unusable for this long, which is why it is
# seconds rather than minutes.
UNKNOWN_KID_TTL_SECONDS = 60

# ponytail: a plain dict with a size cap, not an LRU. The bound is what stops
# an attacker minting unbounded random `kid`s from growing it; swap in
# cachetools.TTLCache if this ever needs eviction by age rather than wholesale.
MAX_UNKNOWN_KIDS = 1024

# Caches the key set and refetches on an unseen `kid`, which is the whole
# reason users can rotate its key without this service being redeployed.
jwks_client = PyJWKClient(settings.JWKS_URL, timeout=JWKS_TIMEOUT_SECONDS)

# `kid` -> when we last proved it was not in the published set.
_unknown_kids: Dict[object, float] = {}


def _signing_key(token: str) -> PyJWK:
    """The published key this token names, or raise.

    PyJWKClient refetches the whole key set whenever a `kid` misses, and the
    `kid` comes off the *unverified* header -- so an anonymous caller can turn
    one request here into one request to the issuer, all day, for free. A `kid`
    we have already proven absent is refused without going back out.
    """
    kid = jwt.get_unverified_header(token).get("kid")
    now = time.monotonic()

    rejected_at = _unknown_kids.get(kid)
    if rejected_at is not None and now - rejected_at < UNKNOWN_KID_TTL_SECONDS:
        raise PyJWKClientError(f'Unable to find a signing key that matches: "{kid}"')

    try:
        return jwks_client.get_signing_key_from_jwt(token)
    except PyJWKClientConnectionError:
        # The issuer is unreachable, which says nothing about this `kid`.
        # Caching it here would turn a blip into a minute of false 401s.
        raise
    except PyJWKClientError:
        if len(_unknown_kids) >= MAX_UNKNOWN_KIDS:
            _unknown_kids.clear()
        _unknown_kids[kid] = now
        raise


async def subject_of(token: str) -> str:
    """Who the issuer says this is, or raise.

    PyJWKClient is synchronous and hits the network on a cache miss, so it goes
    to a thread -- same reason bcrypt does in users.
    """
    key = await asyncio.to_thread(_signing_key, token)
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
