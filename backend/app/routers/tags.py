from fastapi import APIRouter, Depends
from sqlalchemy import select

from ..auth import get_current_user
from ..db import SessionLocal
from ..models import Tag, User
from ..schemas import TagOut

router = APIRouter(prefix="/api", tags=["tags"])


@router.get("/tags", response_model=list[TagOut])
async def list_tags(user: User = Depends(get_current_user)) -> list[TagOut]:
    async with SessionLocal() as session:
        tags = (
            await session.execute(select(Tag).order_by(Tag.type, Tag.label))
        ).scalars().all()
    return [TagOut(key=tag.key, label=tag.label, type=tag.type) for tag in tags]
