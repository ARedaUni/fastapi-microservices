from fastapi import APIRouter, Depends

from app.api.deps import get_token_data

router = APIRouter(prefix="/home", tags=["Home"])


@router.get("/", dependencies=[Depends(get_token_data)])
async def home():
    return "Hello World!"


# Deliberately public: the unauthenticated counterpart to "/" above, kept as
# demo surface. Covered by test_home_another_is_deliberately_public.
@router.get("/another/")
async def another():
    return "Another Hello World!"
