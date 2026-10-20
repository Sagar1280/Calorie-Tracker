from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from ..db import SessionLocal

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "database_unavailable",
                "message": "The database is not available.",
            },
        ) from exc
    return {"status": "ok"}
