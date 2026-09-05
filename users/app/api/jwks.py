from typing import Any, Dict

from fastapi import APIRouter

from app.core.security import PUBLIC_JWK

# Outside /api/v1 on purpose: RFC 8615 reserves /.well-known/ so a verifier
# finds keys without being told a path.
router = APIRouter(tags=["JWKS"])


@router.get("/.well-known/jwks.json")
async def jwks() -> Dict[str, Any]:
    """Public keys, unauthenticated -- needing a credential to fetch one would
    mean needing a credential to check a credential.

    A list, which is the payoff over pasting a PEM into every service: publish
    the new key beside the old, sign with the new, drop the old once every
    token it signed has expired. No verifier redeploys.
    """
    return {"keys": [PUBLIC_JWK]}
