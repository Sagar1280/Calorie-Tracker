from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from .auth import get_current_user
from .db import SessionLocal
from .foods import to_detail_out, to_summary_out
from .models import Brand, Food, FoodAlias, FoodReview, FoodVariant, User
from .schemas import (
    AdminFoodReviewListOut,
    AdminFoodReviewOut,
    AdminFoodUpdateIn,
    FoodDetailOut,
    FoodListOut,
)
from .text import normalize_text, slugify

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "admin_required",
                "message": "Admin access is required for this action.",
            },
        )


async def brand_for_name(session, name: str | None) -> int | None:
    if not name:
        return None

    brand_name = name[:80]
    brand_slug = slugify(brand_name)[:80]
    brand = (
        await session.execute(select(Brand).where(Brand.slug == brand_slug))
    ).scalar_one_or_none()
    if brand is None:
        brand = Brand(name=brand_name, slug=brand_slug)
        session.add(brand)
        await session.flush()
    return brand.id


@router.get("/foods", response_model=FoodListOut)
async def list_admin_foods(
    q: str | None = Query(default=None, max_length=80),
    source: str | None = Query(default=None, max_length=16),
    status: str | None = Query(default=None, max_length=16),
    is_verified: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
) -> FoodListOut:
    require_admin(user)

    async with SessionLocal() as session:
        statement = select(Food)
        if source:
            statement = statement.where(Food.source == normalize_text(source))
        if status:
            statement = statement.where(Food.status == normalize_text(status))
        if is_verified is not None:
            statement = statement.where(Food.is_verified.is_(is_verified))
        if q:
            query = normalize_text(q)
            pattern = f"%{query}%"
            statement = statement.where(
                or_(
                    Food.name_normalized.like(pattern),
                    Food.aliases.any(
                        FoodAlias.alias_normalized.like(pattern)
                    ),
                )
            )

        foods = (await session.execute(statement)).scalars().unique().all()

    foods.sort(key=lambda food: food.id, reverse=True)
    total = len(foods)
    page = foods[offset : offset + limit]
    return FoodListOut(
        items=[to_summary_out(food) for food in page],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.put("/foods/{food_id}", response_model=FoodDetailOut)
async def update_admin_food(
    food_id: int,
    payload: AdminFoodUpdateIn,
    user: User = Depends(get_current_user),
) -> FoodDetailOut:
    require_admin(user)

    async with SessionLocal() as session:
        food = (
            await session.execute(select(Food).where(Food.id == food_id))
        ).scalar_one_or_none()
        if food is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "food_not_found",
                    "message": "That food is not available.",
                },
            )

        variant = next(
            (item for item in food.variants if item.is_default),
            food.variants[0] if food.variants else None,
        )
        if variant is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "food_variant_missing",
                    "message": "That food has no nutrition variant to edit.",
                },
            )

        food.name = payload.name
        food.name_normalized = normalize_text(payload.name)
        food.category = normalize_text(payload.category)
        food.subcategory = payload.subcategory
        food.description = payload.description
        food.status = payload.status
        food.is_verified = payload.is_verified
        food.brand_id = await brand_for_name(session, payload.brand_name)
        food.base_unit = payload.variant.base_unit

        variant.kcal = payload.variant.kcal
        variant.protein_g = payload.variant.protein_g
        variant.carbs_g = payload.variant.carbs_g
        variant.fat_g = payload.variant.fat_g
        variant.base_amount = payload.variant.base_amount
        variant.base_unit = payload.variant.base_unit

        if payload.status == "rejected":
            action = "rejected"
        elif payload.status == "approved" and payload.is_verified:
            action = "approved"
        else:
            action = "updated"
        session.add(
            FoodReview(
                food_id=food.id,
                reviewer_user_id=user.id,
                action=action,
                status=payload.status,
                is_verified=payload.is_verified,
                note=payload.review_note,
            )
        )

        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "food_update_conflict",
                    "message": "That update conflicts with another food or brand.",
                },
            ) from exc

        session.expire_all()
        updated = (
            await session.execute(select(Food).where(Food.id == food_id))
        ).scalar_one()
        return to_detail_out(updated)


@router.get("/foods/{food_id}/reviews", response_model=AdminFoodReviewListOut)
async def list_food_reviews(
    food_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
) -> AdminFoodReviewListOut:
    require_admin(user)

    async with SessionLocal() as session:
        food_exists = (
            await session.execute(select(Food.id).where(Food.id == food_id))
        ).scalar_one_or_none()
        if food_exists is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "food_not_found",
                    "message": "That food is not available.",
                },
            )

        rows = (
            await session.execute(
                select(FoodReview, User.username)
                .outerjoin(User, User.id == FoodReview.reviewer_user_id)
                .where(FoodReview.food_id == food_id)
                .order_by(FoodReview.created_at.desc(), FoodReview.id.desc())
                .limit(limit)
            )
        ).all()

    return AdminFoodReviewListOut(
        items=[
            AdminFoodReviewOut(
                id=review.id,
                action=review.action,
                status=review.status,
                is_verified=review.is_verified,
                note=review.note,
                reviewer_username=username,
                created_at=review.created_at,
            )
            for review, username in rows
        ]
    )
