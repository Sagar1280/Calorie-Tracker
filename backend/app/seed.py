from sqlalchemy import select

from .db import SessionLocal
from .models import Tag

DEFAULT_TAGS: tuple[dict[str, str], ...] = (
    {"key": "iron", "label": "Iron", "type": "micronutrient"},
    {"key": "zinc", "label": "Zinc", "type": "micronutrient"},
    {"key": "calcium", "label": "Calcium", "type": "micronutrient"},
    {"key": "vitamin_b12", "label": "Vitamin B12", "type": "micronutrient"},
    {"key": "vitamin_d", "label": "Vitamin D", "type": "micronutrient"},
    {"key": "vitamin_c", "label": "Vitamin C", "type": "micronutrient"},
    {"key": "folate", "label": "Folate", "type": "micronutrient"},
    {"key": "magnesium", "label": "Magnesium", "type": "micronutrient"},
    {"key": "potassium", "label": "Potassium", "type": "micronutrient"},
    {"key": "omega_3", "label": "Omega-3", "type": "micronutrient"},
    {"key": "vitamin_a", "label": "Vitamin A", "type": "micronutrient"},
    {"key": "vitamin_e", "label": "Vitamin E", "type": "micronutrient"},
)


async def seed_default_tags() -> None:
    async with SessionLocal() as session:
        existing = set(
            (await session.execute(select(Tag.key))).scalars().all()
        )
        for item in DEFAULT_TAGS:
            if item["key"] not in existing:
                session.add(Tag(**item))
        await session.commit()
