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


def is_valid_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(_bcrypt_bytes(plain_password), hashed_password.encode())


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_bytes(password), bcrypt.gensalt()).decode()


async def authenticate(
    session: AsyncSession, email: EmailStr, password: str
) -> Optional[User]:
    user = await crud_user.get(session, email=email)
    # user.hashed_password types as Column[str] under 1.x-style Column(); see the
    # note in models/base.py.
    if user is not None and is_valid_password(
        password,
        user.hashed_password,  # type: ignore[arg-type]
    ):
        return user
    return None
