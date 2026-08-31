import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.users import crud_user
from app.models.users import User

ALGORITHM = "HS256"

# bcrypt hashes at most 72 bytes and raises on anything longer. passlib used to
# truncate silently, so we keep doing that; test_a_password_longer_than_72_bytes
# _is_truncated fails if this goes away.
BCRYPT_MAX_BYTES = 72


def _bcrypt_bytes(password: str) -> bytes:
    return password.encode()[:BCRYPT_MAX_BYTES]


def create_access_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(
        {"exp": expire, "user_id": str(user.id)},
        key=settings.SECRET_KEY.get_secret_value(),
        algorithm=ALGORITHM,
    )


def _hash(password: bytes) -> bytes:
    return bcrypt.hashpw(password, bcrypt.gensalt())


# Both of these are `async` only so they can hand bcrypt to a worker thread.
# Marking them async without that would change nothing: bcrypt is synchronous
# CPU work, and a coroutine that calls it straight through never yields, so the
# event loop stays blocked for the whole hash. `to_thread` is the yield point.
#
# This only helps because bcrypt releases the GIL while hashing; the tests in
# test_security.py fail if that stops being true.
#
# Ceiling: asyncio's default executor, min(32, cpu + 4) threads. That bounds
# concurrent hashes, not the loop -- past it logins queue instead of blocking
# everything else. A dedicated executor is the upgrade if logins ever saturate
# it.
async def is_valid_password(plain_password: str, hashed_password: str) -> bool:
    return await asyncio.to_thread(
        bcrypt.checkpw, _bcrypt_bytes(plain_password), hashed_password.encode()
    )


async def get_password_hash(password: str) -> str:
    hashed = await asyncio.to_thread(_hash, _bcrypt_bytes(password))
    return hashed.decode()


async def authenticate(
    session: AsyncSession, email: EmailStr, password: str
) -> Optional[User]:
    user = await crud_user.get(session, email=email)
    if user is not None and await is_valid_password(password, user.hashed_password):
        return user
    return None
