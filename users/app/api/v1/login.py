from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.security import AUDIENCE, authenticate, create_access_token
from app.schemas.token import Token

router = APIRouter(tags=["Login"])


@router.post("/login/", response_model=Token)
async def login(
    data: OAuth2PasswordRequestForm = Depends(),
    # One service, by name (RFC 8693's `audience`, not RFC 8707's `resource`,
    # which must be an absolute URI). Shape-checked, not looked up: a name no
    # service pins yields a token nothing accepts, which harms no one.
    audience: str = Form(AUDIENCE, pattern=r"^[a-z][a-z0-9-]*$"),
    session: AsyncSession = Depends(get_session),
):
    user = await authenticate(session, email=data.username, password=data.password)
    if user is None:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return {"access_token": create_access_token(user, audience), "token_type": "bearer"}
