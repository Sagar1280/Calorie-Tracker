import secrets
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from .auth import get_current_user
from .config import ADMIN_CONFIRM_PASSWORD
from .db import SessionLocal
from .foods import to_detail_out, to_summary_out
from .limiter import enforce_rate_limit
from .models import Brand, Food, FoodAlias, FoodReview, FoodVariant, User
from .schemas import (
    AdminBulkActionIn,
    AdminBulkResultOut,
    AdminFoodCreateIn,
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


async def require_admin_password(
    password: str | None = Header(default=None, alias="X-Admin-Password"),
    user: User = Depends(get_current_user),
) -> None:
    if not ADMIN_CONFIRM_PASSWORD:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "admin_password_not_configured",
                "message": (
                    "Admin confirmation is not configured. Set "
                    "ADMIN_CONFIRM_PASSWORD on the server."
                ),
            },
        )
    if not password or not secrets.compare_digest(
        password, ADMIN_CONFIRM_PASSWORD
    ):
        enforce_rate_limit(
            "admin-confirm",
            str(user.id),
            limit=5,
            window_seconds=300,
            message="Too many incorrect admin passwords. Wait five minutes.",
        )
        raise HTTPException(
            status_code=403,
            detail={
                "code": "admin_password_invalid",
                "message": "That confirmation password is incorrect.",
            },
        )


def review_action(status: str, is_verified: bool) -> str:
    if status == "rejected":
        return "rejected"
    if status == "approved" and is_verified:
        return "approved"
    return "updated"


async def unique_slug(session, value: str) -> str:
    base = slugify(value)[:140].rstrip("-") or "food"
    candidate = base
    if (
        await session.execute(select(Food.id).where(Food.slug == candidate))
    ).scalar_one_or_none() is not None:
        candidate = f"{base}-{uuid4().hex[:6]}"
    return candidate


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


@router.post("/foods", response_model=FoodDetailOut, status_code=201)
async def create_admin_food(
    payload: AdminFoodCreateIn,
    user: User = Depends(get_current_user),
    _password: None = Depends(require_admin_password),
) -> FoodDetailOut:
    require_admin(user)

    async with SessionLocal() as session:
        brand_id = await brand_for_name(session, payload.brand_name)
        food = Food(
            slug=await unique_slug(
                session, f"{payload.brand_name or ''} {payload.name}"
            ),
            name=payload.name,
            name_normalized=normalize_text(payload.name)[:160],
            category=normalize_text(payload.category),
            subcategory=payload.subcategory,
            brand_id=brand_id,
            base_unit=payload.variant.base_unit,
            description=payload.description,
            source="curated",
            status=payload.status,
            is_verified=payload.is_verified,
            created_by_user_id=user.id,
        )
        session.add(food)
        await session.flush()

        variant = FoodVariant(
            food_id=food.id,
            state="as_sold",
            label="",
            kcal=payload.variant.kcal,
            protein_g=payload.variant.protein_g,
            carbs_g=payload.variant.carbs_g,
            fat_g=payload.variant.fat_g,
            base_amount=payload.variant.base_amount,
            base_unit=payload.variant.base_unit,
            is_default=True,
        )
        session.add(variant)
        session.add(
            FoodReview(
                food_id=food.id,
                reviewer_user_id=user.id,
                action=review_action(payload.status, payload.is_verified),
                status=payload.status,
                is_verified=payload.is_verified,
                note=payload.review_note or "Created from the admin review screen.",
            )
        )

        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "food_create_conflict",
                    "message": "That food conflicts with an existing food or brand.",
                },
            ) from exc

        food_id = food.id
        session.expire_all()
        created = (
            await session.execute(select(Food).where(Food.id == food_id))
        ).scalar_one()
        return to_detail_out(created)


@router.post("/foods/bulk", response_model=AdminBulkResultOut)
async def bulk_admin_foods(
    payload: AdminBulkActionIn,
    user: User = Depends(get_current_user),
    _password: None = Depends(require_admin_password),
) -> AdminBulkResultOut:
    require_admin(user)

    async with SessionLocal() as session:
        foods = (
            (
                await session.execute(
                    select(Food).where(Food.id.in_(payload.ids))
                )
            )
            .scalars()
            .unique()
            .all()
        )
        if not foods:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "foods_not_found",
                    "message": "None of those foods are available.",
                },
            )

        affected_ids: list[int] = []
        for food in foods:
            affected_ids.append(food.id)
            if payload.action == "delete":
                await session.delete(food)
                continue

            if payload.action == "approve":
                food.status = "approved"
                food.is_verified = True
                action = "approved"
            else:
                food.status = "rejected"
                food.is_verified = False
                action = "rejected"

            session.add(
                FoodReview(
                    food_id=food.id,
                    reviewer_user_id=user.id,
                    action=action,
                    status=food.status,
                    is_verified=food.is_verified,
                    note=payload.review_note or (
                        "Approved from the admin review screen."
                        if action == "approved"
                        else "Rejected from the admin review screen."
                    ),
                )
            )

        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "bulk_action_conflict",
                    "message": "That bulk action conflicts with existing data.",
                },
            ) from exc

    return AdminBulkResultOut(
        action=payload.action,
        food_ids=affected_ids,
        affected=len(affected_ids),
    )


@router.put("/foods/{food_id}", response_model=FoodDetailOut)
async def update_admin_food(
    food_id: int,
    payload: AdminFoodUpdateIn,
    user: User = Depends(get_current_user),
    _password: None = Depends(require_admin_password),
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

        session.add(
            FoodReview(
                food_id=food.id,
                reviewer_user_id=user.id,
                action=review_action(payload.status, payload.is_verified),
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


@router.delete("/foods/{food_id}", status_code=204)
async def delete_admin_food(
    food_id: int,
    user: User = Depends(get_current_user),
    _password: None = Depends(require_admin_password),
) -> Response:
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

        await session.delete(food)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "food_delete_conflict",
                    "message": "That food is still referenced and cannot be deleted.",
                },
            ) from exc

    return Response(status_code=204)


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
