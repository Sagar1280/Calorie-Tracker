from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..calories import daily_calorie_goal, daily_nutrition_targets
from ..models import CalorieEntry, DayLog, Profile
from ..schemas import (
    CalorieEntryOut,
    DayLogOut,
    MonthDayOut,
    MonthLogOut,
)
from ..serializers import with_utc


def to_entry_out(entry: CalorieEntry) -> CalorieEntryOut:
    return CalorieEntryOut(
        id=entry.id,
        date=entry.entry_date,
        meal=entry.meal,
        name=entry.name,
        calories=entry.calories,
        variant_id=entry.variant_id,
        quantity=entry.quantity,
        unit=entry.unit,
        protein_g=entry.protein_g_snapshot,
        fat_g=entry.fat_g_snapshot,
        created_at=with_utc(entry.created_at),
    )


def day_locked() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "day_locked",
            "message": "This day is complete. Reopen it to make changes.",
        },
    )


async def ensure_day_editable(
    session: AsyncSession, user_id: int, target: date
) -> None:
    day_log = (
        await session.execute(
            select(DayLog).where(
                DayLog.user_id == user_id,
                DayLog.log_date == target,
            )
        )
    ).scalar_one_or_none()
    if day_log is not None and day_log.done:
        raise day_locked()


async def build_day_log(
    session: AsyncSession, user_id: int, target: date
) -> DayLogOut:
    profile = (
        await session.execute(select(Profile).where(Profile.user_id == user_id))
    ).scalar_one_or_none()
    goal, goal_source = daily_calorie_goal(profile)
    targets = daily_nutrition_targets(profile, goal)

    rows = (
        await session.execute(
            select(CalorieEntry)
            .where(
                CalorieEntry.user_id == user_id,
                CalorieEntry.entry_date == target,
            )
            .order_by(CalorieEntry.created_at, CalorieEntry.id)
        )
    ).scalars().all()

    day_log = (
        await session.execute(
            select(DayLog).where(
                DayLog.user_id == user_id,
                DayLog.log_date == target,
            )
        )
    ).scalar_one_or_none()

    consumed = sum(row.calories or 0 for row in rows)
    protein_consumed = round(
        sum(row.protein_g_snapshot or 0 for row in rows), 1
    )
    fat_consumed = round(sum(row.fat_g_snapshot or 0 for row in rows), 1)
    return DayLogOut(
        date=target,
        goal=goal,
        goal_source=goal_source,
        consumed=consumed,
        remaining=goal - consumed,
        done=bool(day_log and day_log.done),
        protein_goal_g=targets.protein_g,
        fat_goal_g=targets.fat_g,
        water_goal_ml=targets.water_ml,
        protein_consumed_g=protein_consumed,
        fat_consumed_g=fat_consumed,
        entries=[to_entry_out(row) for row in rows],
    )


async def build_month_log(
    session: AsyncSession, user_id: int, year: int, month: int
) -> MonthLogOut:
    first = date(year, month, 1)
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    profile = (
        await session.execute(select(Profile).where(Profile.user_id == user_id))
    ).scalar_one_or_none()
    goal, goal_source = daily_calorie_goal(profile)

    rows = (
        await session.execute(
            select(CalorieEntry)
            .where(
                CalorieEntry.user_id == user_id,
                CalorieEntry.entry_date >= first,
                CalorieEntry.entry_date < next_month,
            )
            .order_by(CalorieEntry.entry_date, CalorieEntry.created_at)
        )
    ).scalars().all()

    done_dates = set(
        (
            await session.execute(
                select(DayLog.log_date).where(
                    DayLog.user_id == user_id,
                    DayLog.log_date >= first,
                    DayLog.log_date < next_month,
                    DayLog.done.is_(True),
                )
            )
        ).scalars().all()
    )

    buckets: dict[date, list[CalorieEntry]] = {}
    for row in rows:
        buckets.setdefault(row.entry_date, []).append(row)

    all_dates = sorted(set(buckets) | done_dates)
    days = [
        MonthDayOut(
            date=day,
            consumed=sum(entry.calories or 0 for entry in buckets.get(day, [])),
            entries=len(buckets.get(day, [])),
            done=day in done_dates,
        )
        for day in all_dates
    ]
    total_consumed = sum(day.consumed for day in days)
    days_logged = sum(1 for day in days if day.entries > 0)

    return MonthLogOut(
        year=year,
        month=month,
        goal=goal,
        goal_source=goal_source,
        days=days,
        total_consumed=total_consumed,
        days_logged=days_logged,
        average_consumed=round(total_consumed / days_logged, 1) if days_logged else 0.0,
        days_over_goal=sum(1 for day in days if day.consumed > goal),
    )
