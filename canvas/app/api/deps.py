from app.core.database import SessionLocal


async def get_session():
    async with SessionLocal() as session:
        yield session
