import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import ALGORITHM, AUDIENCE, PUBLIC_KEY
from app.crud.users import crud_user
from app.models.users import User
from app.schemas.token import TokenPayload

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/login")


async def get_session():
    async with SessionLocal() as session:
        yield session


def get_token_data(token: str = Depends(oauth2)) -> TokenPayload:
    try:
        # algorithms is pinned, never read from the header: the public key is
        # published, so a verifier that trusted `alg` would accept an HS256
        # token signed with that key as the HMAC secret.
        payload = jwt.decode(
            token,
            key=PUBLIC_KEY,
            algorithms=[ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=AUDIENCE,
        )
        token_data = TokenPayload(**payload)
    except (jwt.PyJWTError, ValidationError):
        raise HTTPException(status_code=403, detail="Could not validate credentials")
    return token_data


async def get_current_user(
    token: TokenPayload = Depends(get_token_data),
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await crud_user.get(session, id=token.sub)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


def get_current_superuser(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user


on_superuser = get_current_superuser
