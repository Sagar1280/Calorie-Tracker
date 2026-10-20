from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, or_, select
from sqlalchemy.exc import IntegrityError

from .auth import get_current_user
from .db import SessionLocal
from .limiter import enforce_rate_limit
from .models import (
    Brand,
    Food,
    FoodAlias,
    FoodBarcode,
    FoodVariant,
    Serving,
    Tag,
    User,
)
from .openfoodfacts import OffProduct, OpenFoodFactsError, lookup_off_product
from .schemas import (
    BarcodeLookupIn,
    BarcodeOut,
    BrandOut,
    FoodDetailOut,
    FoodListOut,
    FoodSummaryOut,
    ServingOut,
    TagOut,
    VariantOut,
)
from .text import normalize_text, slugify

router = APIRouter(prefix="/api/foods", tags=["foods"])


def can_view(food: Food, user: User) -> bool:
    return (
        food.status == "approved"
        or food.created_by_user_id == user.id
        or user.role == "admin"
    )


def to_tag_out(tag: Tag) -> TagOut:
    return TagOut(key=tag.key, label=tag.label, type=tag.type)


def to_serving_out(serving) -> ServingOut:
    return ServingOut(
        id=serving.id,
        label=serving.label,
        amount=serving.amount,
        unit=serving.unit,
        is_default=serving.is_default,
    )


def to_variant_out(variant) -> VariantOut:
    return VariantOut(
        id=variant.id,
        state=variant.state,
        label=variant.label,
        kcal=variant.kcal,
        protein_g=variant.protein_g,
        carbs_g=variant.carbs_g,
        fat_g=variant.fat_g,
        base_amount=variant.base_amount,
        base_unit=variant.base_unit,
        is_default=variant.is_default,
        servings=[to_serving_out(serving) for serving in variant.servings],
    )


def default_variant(food: Food):
    for variant in food.variants:
        if variant.is_default:
            return variant
    return food.variants[0] if food.variants else None


def to_summary_out(food: Food) -> FoodSummaryOut:
    variant = default_variant(food)
    return FoodSummaryOut(
        id=food.id,
        slug=food.slug,
        name=food.name,
        category=food.category,
        subcategory=food.subcategory,
        brand=(
            BrandOut(id=food.brand.id, name=food.brand.name, slug=food.brand.slug)
            if food.brand
            else None
        ),
        base_unit=food.base_unit,
        region=food.region,
        source=food.source,
        status=food.status,
        is_verified=food.is_verified,
        tags=[to_tag_out(tag) for tag in food.tags],
        default_variant=to_variant_out(variant) if variant else None,
    )


def to_detail_out(food: Food) -> FoodDetailOut:
    summary = to_summary_out(food)
    return FoodDetailOut(
        **summary.model_dump(),
        description=food.description,
        variants=[to_variant_out(variant) for variant in food.variants],
        aliases=[alias.alias for alias in food.aliases],
        barcodes=[
            BarcodeOut(
                id=barcode.id,
                barcode=barcode.barcode,
                pack_amount=barcode.pack_amount,
                pack_unit=barcode.pack_unit,
                source=barcode.source,
                variant_id=barcode.variant_id,
            )
            for barcode in food.barcodes
        ],
    )


async def _find_barcode_food(session, barcode: str) -> Food | None:
    barcode_row = (
        await session.execute(
            select(FoodBarcode).where(FoodBarcode.barcode == barcode)
        )
    ).scalar_one_or_none()
    if barcode_row is None:
        return None
    return (
        await session.execute(select(Food).where(Food.id == barcode_row.food_id))
    ).scalar_one_or_none()


def _barcode_not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "barcode_not_found",
            "message": "No product was found for that barcode yet.",
        },
    )


async def _import_off_product(product: OffProduct, user: User) -> FoodDetailOut:
    async with SessionLocal() as session:
        existing = await _find_barcode_food(session, product.barcode)
        if existing is not None:
            if not can_view(existing, user):
                raise _barcode_not_found()
            return to_detail_out(existing)

        brand_id = None
        if product.brand:
            brand_name = product.brand[:80]
            brand_slug = slugify(brand_name)[:80]
            brand = (
                await session.execute(
                    select(Brand).where(Brand.slug == brand_slug)
                )
            ).scalar_one_or_none()
            if brand is None:
                brand = Brand(name=brand_name, slug=brand_slug)
                session.add(brand)
                await session.flush()
            brand_id = brand.id

        base_unit = product.pack_unit or "g"
        name = product.name[:160]
        base_slug = slugify(f"{product.brand or ''} {name}")[:140].rstrip("-")
        slug = f"{base_slug}-off-{product.barcode}"[:160]

        food = Food(
            slug=slug,
            name=name,
            name_normalized=normalize_text(name)[:160],
            category="packaged",
            brand_id=brand_id,
            base_unit=base_unit,
            source="off",
            source_ref=f"https://world.openfoodfacts.org/product/{product.barcode}",
            description=(
                "Imported from Open Food Facts. Nutrition is crowd-sourced "
                "and has not been verified."
            ),
            status="approved",
            is_verified=False,
        )
        session.add(food)
        await session.flush()

        variant = FoodVariant(
            food_id=food.id,
            state="as_sold",
            label="",
            kcal=product.kcal,
            protein_g=product.protein_g,
            carbs_g=product.carbs_g,
            fat_g=product.fat_g,
            base_amount=100,
            base_unit=base_unit,
            is_default=True,
        )
        session.add(variant)
        await session.flush()

        if product.pack_amount is not None and product.pack_unit:
            session.add(
                Serving(
                    variant_id=variant.id,
                    label="1 pack",
                    amount=product.pack_amount,
                    unit=product.pack_unit,
                    is_default=True,
                )
            )

        session.add(
            FoodBarcode(
                food_id=food.id,
                variant_id=variant.id,
                barcode=product.barcode,
                pack_amount=product.pack_amount,
                pack_unit=product.pack_unit,
                source="off",
            )
        )

        food_id = food.id
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            existing = await _find_barcode_food(session, product.barcode)
            if existing is not None and can_view(existing, user):
                return to_detail_out(existing)
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "barcode_conflict",
                    "message": "That barcode is already linked to another food.",
                },
            ) from exc

        imported = (
            await session.execute(select(Food).where(Food.id == food_id))
        ).scalar_one()
        return to_detail_out(imported)


def match_score(food: Food, query: str) -> int:
    name = food.name_normalized
    aliases = [alias.alias_normalized for alias in food.aliases]

    if name == query:
        return 0
    if name.startswith(query):
        return 1
    if query in name:
        return 2
    if query in aliases:
        return 3
    if any(alias.startswith(query) for alias in aliases):
        return 4
    return 5


@router.get("", response_model=FoodListOut)
async def search_foods(
    q: str | None = Query(default=None, max_length=80),
    category: str | None = Query(default=None, max_length=32),
    brand: str | None = Query(default=None, max_length=80),
    tag: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
) -> FoodListOut:
    query = normalize_text(q) if q else ""

    async with SessionLocal() as session:
        statement = select(Food)
        if user.role != "admin":
            statement = statement.where(
                or_(
                    Food.status == "approved",
                    Food.created_by_user_id == user.id,
                )
            )
        if category:
            statement = statement.where(
                Food.category == normalize_text(category)
            )
        if brand:
            statement = statement.where(
                Food.brand.has(Brand.slug == slugify(brand))
            )
        if tag:
            statement = statement.where(
                Food.tags.any(Tag.key == normalize_text(tag))
            )
        if query:
            pattern = f"%{query}%"
            alias_match = exists().where(
                FoodAlias.food_id == Food.id,
                FoodAlias.alias_normalized.like(pattern),
            )
            statement = statement.where(
                or_(Food.name_normalized.like(pattern), alias_match)
            )

        foods = (await session.execute(statement)).scalars().unique().all()

    if query:
        foods.sort(
            key=lambda food: (
                match_score(food, query),
                not food.is_verified,
                food.name_normalized,
            )
        )
    else:
        foods.sort(
            key=lambda food: (not food.is_verified, food.name_normalized)
        )

    total = len(foods)
    page = foods[offset : offset + limit]
    return FoodListOut(
        items=[to_summary_out(food) for food in page],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/barcode/resolve", response_model=FoodDetailOut)
async def resolve_barcode(
    payload: BarcodeLookupIn,
    user: User = Depends(get_current_user),
) -> FoodDetailOut:
    async with SessionLocal() as session:
        existing = await _find_barcode_food(session, payload.barcode)

    if existing is not None:
        if not can_view(existing, user):
            raise _barcode_not_found()
        return to_detail_out(existing)

    enforce_rate_limit("barcode", user.id, limit=12, window_seconds=60)

    try:
        product = await lookup_off_product(payload.barcode)
    except OpenFoodFactsError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "barcode_service_unavailable",
                "message": (
                    "Barcode lookup is unavailable right now. "
                    "Try search or manual entry."
                ),
            },
        ) from exc

    if product is None:
        raise _barcode_not_found()

    return await _import_off_product(product, user)


@router.get("/barcode/{barcode}", response_model=FoodDetailOut)
async def get_food_by_barcode(
    barcode: str,
    user: User = Depends(get_current_user),
) -> FoodDetailOut:
    normalized_barcode = barcode.strip()

    async with SessionLocal() as session:
        barcode_row = (
            await session.execute(
                select(FoodBarcode).where(
                    FoodBarcode.barcode == normalized_barcode
                )
            )
        ).scalar_one_or_none()

        if barcode_row is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "barcode_not_found",
                    "message": "No food is linked to that barcode yet.",
                },
            )

        food = (
            await session.execute(select(Food).where(Food.id == barcode_row.food_id))
        ).scalar_one()

        if not can_view(food, user):
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "food_not_found",
                    "message": "That food is not available.",
                },
            )

        return to_detail_out(food)


@router.get("/{food_id}", response_model=FoodDetailOut)
async def get_food(
    food_id: int,
    user: User = Depends(get_current_user),
) -> FoodDetailOut:
    async with SessionLocal() as session:
        food = (
            await session.execute(select(Food).where(Food.id == food_id))
        ).scalar_one_or_none()

    if food is None or not can_view(food, user):
        raise HTTPException(
            status_code=404,
            detail={
                "code": "food_not_found",
                "message": "That food is not available.",
            },
        )

    return to_detail_out(food)
