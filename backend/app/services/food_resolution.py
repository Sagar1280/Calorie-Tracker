from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Food, FoodAlias, FoodVariant
from ..photo_llm import MealPhotoItem
from ..text import normalize_text, slugify


@dataclass(frozen=True)
class ResolvedPhotoItem:
    name: str
    portion_g: float
    calories: int
    protein_g: float
    carbs_g: float
    fat_g: float
    confidence: float
    matched: bool
    food_id: int | None
    variant_id: int | None
    unit: str

    def as_job_item(self) -> dict[str, object]:
        return {
            "name": self.name,
            "portion_g": self.portion_g,
            "calories": self.calories,
            "protein_g": self.protein_g,
            "carbs_g": self.carbs_g,
            "fat_g": self.fat_g,
            "confidence": self.confidence,
            "matched": self.matched,
            "food_id": self.food_id,
        }


def _default_variant(food: Food) -> FoodVariant | None:
    for variant in food.variants:
        if variant.is_default:
            return variant
    return food.variants[0] if food.variants else None


def _name_candidates(name: str) -> list[str]:
    normalized = normalize_text(name)[:160]
    candidates = [normalized]
    if len(normalized) > 3 and normalized.endswith("s"):
        candidates.append(normalized[:-1])
    return candidates


async def find_approved_food(
    session: AsyncSession, name: str
) -> Food | None:
    candidates = _name_candidates(name)
    food = (
        (
            await session.execute(
                select(Food)
                .where(
                    Food.status == "approved",
                    Food.name_normalized.in_(candidates),
                )
                .order_by(Food.is_verified.desc(), Food.id)
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if food is not None:
        return food

    return (
        (
            await session.execute(
                select(Food)
                .join(FoodAlias, FoodAlias.food_id == Food.id)
                .where(
                    Food.status == "approved",
                    FoodAlias.alias_normalized.in_(candidates),
                )
                .order_by(Food.is_verified.desc(), Food.id)
                .limit(1)
            )
        )
        .scalars()
        .unique()
        .first()
    )


def _from_database(
    item: MealPhotoItem, food: Food, variant: FoodVariant
) -> ResolvedPhotoItem:
    factor = item.portion_g / variant.base_amount
    return ResolvedPhotoItem(
        name=food.name,
        portion_g=round(item.portion_g, 1),
        calories=max(0, min(10000, round((variant.kcal or 0) * factor))),
        protein_g=round((variant.protein_g or 0) * factor, 1),
        carbs_g=round((variant.carbs_g or 0) * factor, 1),
        fat_g=round((variant.fat_g or 0) * factor, 1),
        confidence=item.confidence,
        matched=True,
        food_id=food.id,
        variant_id=variant.id,
        unit=food.base_unit,
    )


def _from_estimate(
    item: MealPhotoItem,
    food_id: int | None = None,
    variant_id: int | None = None,
) -> ResolvedPhotoItem:
    return ResolvedPhotoItem(
        name=item.name,
        portion_g=round(item.portion_g, 1),
        calories=item.calories,
        protein_g=round(item.protein_g, 1),
        carbs_g=round(item.carbs_g, 1),
        fat_g=round(item.fat_g, 1),
        confidence=item.confidence,
        matched=False,
        food_id=food_id,
        variant_id=variant_id,
        unit="g",
    )


async def _draft_slug(session: AsyncSession, name: str) -> str:
    base = slugify(name)[:140].rstrip("-") or "photo-food"
    if (
        await session.execute(select(Food.id).where(Food.slug == base))
    ).scalar_one_or_none() is None:
        return base
    return f"{base}-{uuid4().hex[:6]}"


async def _pending_draft(
    session: AsyncSession, name: str
) -> tuple[Food, FoodVariant | None] | None:
    food = (
        (
            await session.execute(
                select(Food)
                .where(
                    Food.name_normalized == normalize_text(name)[:160],
                    Food.status == "pending",
                    Food.source == "user",
                )
                .order_by(Food.id)
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if food is None:
        return None
    return food, _default_variant(food)


async def _create_draft(
    session: AsyncSession,
    user_id: int,
    job_id: int,
    item: MealPhotoItem,
) -> tuple[Food, FoodVariant]:
    factor = 100 / item.portion_g
    food = Food(
        slug=await _draft_slug(session, item.name),
        name=item.name,
        name_normalized=normalize_text(item.name)[:160],
        category="photo",
        base_unit="g",
        description=(
            "Created from a photo meal estimate. Review the nutrition before "
            "approving."
        ),
        source="user",
        source_ref=f"photo-job:{job_id}",
        status="pending",
        is_verified=False,
        created_by_user_id=user_id,
    )
    session.add(food)
    await session.flush()

    variant = FoodVariant(
        food_id=food.id,
        state="as_sold",
        label="",
        kcal=max(0, min(10000, round(item.calories * factor))),
        protein_g=round(item.protein_g * factor, 1),
        carbs_g=round(item.carbs_g * factor, 1),
        fat_g=round(item.fat_g * factor, 1),
        base_amount=100,
        base_unit="g",
        is_default=True,
    )
    session.add(variant)
    await session.flush()
    return food, variant


async def resolve_photo_item(
    session: AsyncSession,
    user_id: int,
    job_id: int,
    item: MealPhotoItem,
) -> ResolvedPhotoItem:
    food = await find_approved_food(session, item.name)
    if food is not None:
        variant = _default_variant(food)
        if (
            variant is not None
            and variant.kcal is not None
            and variant.base_amount > 0
        ):
            return _from_database(item, food, variant)
        return _from_estimate(item, food_id=food.id)

    draft = await _pending_draft(session, item.name)
    if draft is None:
        draft_food, draft_variant = await _create_draft(
            session, user_id, job_id, item
        )
        return _from_estimate(item, draft_food.id, draft_variant.id)

    draft_food, draft_variant = draft
    return _from_estimate(
        item,
        draft_food.id,
        draft_variant.id if draft_variant is not None else None,
    )
