from typing import Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import PyJWKClientConnectionError

from app.adapters.redis_publisher import get_instance as get_redis_publisher
from app.core.database import SessionLocal
from app.core.security import subject_of
from app.ports.publisher import Publisher
from app.ports.subscriber import Subscriber

# HTTPBearer, not OAuth2PasswordBearer: there is no login endpoint here to
# point a tokenUrl at. auto_error=False so a missing token is 401 rather than
# FastAPI's 403.
bearer = HTTPBearer(auto_error=False)


async def get_session():
    async with SessionLocal() as session:
        yield session


def get_publisher() -> Publisher:
    return get_redis_publisher()


def get_subscriber() -> Subscriber:
    return get_redis_publisher()


async def current_subject(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return await subject_of(credentials.credentials)
    except PyJWKClientConnectionError:
        # The issuer is unreachable, so we cannot say whether this token is
        # good. 401 would send the caller off to log in again, which also
        # fails; 503 says the truth, that the problem is ours.
        raise HTTPException(status_code=503, detail="Cannot reach the issuer")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
