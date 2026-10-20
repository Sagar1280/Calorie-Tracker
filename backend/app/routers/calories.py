from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from ..auth import get_current_user
from ..concurrency import write_lock
from ..db import SessionLocal
from ..foods import can_view
from ..models import (
    CalorieEntry,
    DayLog,
    Food,
    FoodVariant,
    User,
    utc_now,
)
from ..schemas import (
    CalorieEntryIn,
    CalorieEntryOut,
    DayDoneIn,
    DayLogOut,
    MonthLogOut,
)
from ..services.calories import (
    build_day_log,
    build_month_log,
    ensure_day_editable,
    to_entry_out,
)

router = APIRouter(prefix="/api/calories", tags=["calories"])


@router.get("/day", response_model=DayLogOut)
async def get_day(
    target: date = Query(..., alias="date"),
    user: User = Depends(get_current_user),
) -> DayLogOut:
    async with SessionLocal() as session:
        return await build_day_log(session, user.id, target)


@router.get("/month", response_model=MonthLogOut)
async def get_month(
    year: int,
    month: int,
    user: User = Depends(get_current_user),
) -> MonthLogOut:
    if not 1 <= month <= 12:
        raise HTTPException(status_code=422, detail="Invalid month")
    if not 2000 <= year <= 2100:
        raise HTTPException(status_code=422, detail="Invalid year")
    async with SessionLocal() as session:
        return await build_month_log(session, user.id, year, month)


@router.post("/entries", response_model=CalorieEntryOut, status_code=201)
async def add_calorie_entry(
    payload: CalorieEntryIn, user: User = Depends(get_current_user)
) -> CalorieEntryOut:
    async with write_lock:
        async with SessionLocal() as session:
            await ensure_day_editable(session, user.id, payload.date)

            if payload.variant_id is not None:
                variant = (
                    await session.execute(
                        select(FoodVariant).where(
                            FoodVariant.id == payload.variant_id
                        )
                    )
                ).scalar_one_or_none()
                if variant is None:
                    raise HTTPException(
                        status_code=404,
                        detail={
                            "code": "variant_not_found",
                            "message": "That food portion is not available.",
                        },
                    )

                food = (
                    await session.execute(
                        select(Food).where(Food.id == variant.food_id)
                    )
                ).scalar_one()
                if not can_view(food, user):
                    raise HTTPException(
                        status_code=404,
                        detail={
                            "code": "food_not_found",
                            "message": "That food is not available.",
                        },
                    )

                if variant.base_amount is None or variant.base_amount <= 0:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "code": "invalid_portion",
                            "message": "This food has an invalid portion size.",
                        },
                    )
                if variant.kcal is None:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "code": "nutrition_unavailable",
                            "message": "Calories are unavailable for this food.",
                        },
                    )

                unit = payload.unit or variant.base_unit
                quantity = payload.quantity

                if unit == "pack":
                    serving = next(
                        (item for item in variant.servings if item.is_default),
                        variant.servings[0] if variant.servings else None,
                    )
                    if serving is None:
                        raise HTTPException(
                            status_code=422,
                            detail={
                                "code": "pack_unavailable",
                                "message": "This food has no pack size yet. Use grams or millilitres.",
                            },
                        )
                    packs = quantity if quantity is not None else 1
                    if packs > 100:
                        raise HTTPException(
                            status_code=422,
                            detail={
                                "code": "quantity_too_large",
                                "message": "That quantity is too large to log.",
                            },
                        )
                    quantity = serving.amount * packs
                    unit = serving.unit

                if quantity is None:
                    quantity = variant.base_amount

                if unit not in {"g", "ml"} or unit != variant.base_unit:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "code": "unit_mismatch",
                            "message": f"Use {variant.base_unit} for this food.",
                        },
                    )

                factor = quantity / variant.base_amount
                calories = round(variant.kcal * factor)
                if calories > 10000:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "code": "quantity_too_large",
                            "message": "That quantity is too large to log.",
                        },
                    )

                entry = CalorieEntry(
                    user_id=user.id,
                    entry_date=payload.date,
                    meal=payload.meal,
                    name=(payload.name or food.name)[:120],
                    calories=calories,
                    variant_id=variant.id,
                    quantity=quantity,
                    unit=unit,
                    protein_g_snapshot=round((variant.protein_g or 0) * factor, 1),
                    carbs_g_snapshot=round((variant.carbs_g or 0) * factor, 1),
                    fat_g_snapshot=round((variant.fat_g or 0) * factor, 1),
                    created_at=utc_now(),
                )
            else:
                if payload.name is None or payload.calories is None:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "code": "entry_incomplete",
                            "message": "Choose a food or enter a name and calories.",
                        },
                    )

                entry = CalorieEntry(
                    user_id=user.id,
                    entry_date=payload.date,
                    meal=payload.meal,
                    name=payload.name,
                    calories=payload.calories,
                    created_at=utc_now(),
                )

            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            return to_entry_out(entry)


@router.delete("/entries/{entry_id}", status_code=204)
async def delete_calorie_entry(
    entry_id: int, user: User = Depends(get_current_user)
) -> None:
    async with write_lock:
        async with SessionLocal() as session:
            entry = (
                await session.execute(
                    select(CalorieEntry).where(
                        CalorieEntry.id == entry_id,
                        CalorieEntry.user_id == user.id,
                    )
                )
            ).scalar_one_or_none()
            if entry is None:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "code": "entry_not_found",
                        "message": "That entry was not found.",
                    },
                )
            await ensure_day_editable(session, user.id, entry.entry_date)
            await session.delete(entry)
            await session.commit()


@router.put("/day/done", response_model=DayLogOut)
async def set_day_done(
    payload: DayDoneIn, user: User = Depends(get_current_user)
) -> DayLogOut:
    async with write_lock:
        async with SessionLocal() as session:
            day_log = (
                await session.execute(
                    select(DayLog).where(
                        DayLog.user_id == user.id,
                        DayLog.log_date == payload.date,
                    )
                )
            ).scalar_one_or_none()

            if day_log is None:
                day_log = DayLog(
                    user_id=user.id,
                    log_date=payload.date,
                    done=payload.done,
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
                session.add(day_log)
            else:
                day_log.done = payload.done
                day_log.updated_at = utc_now()

            await session.commit()
            return await build_day_log(session, user.id, payload.date)
