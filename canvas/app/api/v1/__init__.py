from fastapi import APIRouter

from app.api.v1.claims import router as claims_router

router = APIRouter(prefix="/v1")
router.include_router(claims_router)
