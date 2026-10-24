import asyncio
import logging
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from ..concurrency import write_lock
from ..db import SessionLocal
from ..models import CalorieEntry, PhotoMealJob, utc_now
from ..photo_llm import PhotoAnalysisError, analyze_meal_photo
from .calories import ensure_day_editable
from .food_resolution import resolve_photo_item

logger = logging.getLogger(__name__)


async def _mark_failed(job_id: int, message: str) -> None:
    async with SessionLocal() as session:
        job = await session.get(PhotoMealJob, job_id)
        if job is None:
            return
        job.status = "failed"
        job.error = message
        job.image_path = None
        job.updated_at = utc_now()
        job.completed_at = utc_now()
        await session.commit()


async def process_photo_job(job_id: int) -> None:
    async with SessionLocal() as session:
        job = await session.get(PhotoMealJob, job_id)
        if job is None or job.status != "pending":
            return
        job.status = "processing"
        job.updated_at = utc_now()
        await session.commit()

    async with SessionLocal() as session:
        job = await session.get(PhotoMealJob, job_id)
        if job is None:
            return
        image_path_value = job.image_path
        target_date = job.entry_date
        meal = job.meal
        user_id = job.user_id

    if not image_path_value:
        await _mark_failed(job_id, "The meal photo was not available.")
        return

    image_path = Path(image_path_value)
    try:
        image = await asyncio.to_thread(image_path.read_bytes)
        mime_type = (
            "image/png"
            if image.startswith(b"\x89PNG\r\n\x1a\n")
            else "image/webp"
            if image.startswith(b"RIFF") and image[8:12] == b"WEBP"
            else "image/jpeg"
        )
        items = await analyze_meal_photo(image, mime_type)

        async with write_lock:
            async with SessionLocal() as session:
                job = await session.get(PhotoMealJob, job_id)
                if job is None:
                    return
                await ensure_day_editable(session, user_id, target_date)
                entries: list[CalorieEntry] = []
                resolved_items = []
                now = utc_now()
                for item in items:
                    resolved = await resolve_photo_item(
                        session, user_id, job_id, item
                    )
                    resolved_items.append(resolved.as_job_item())
                    entry = CalorieEntry(
                        user_id=user_id,
                        entry_date=target_date,
                        meal=meal,
                        name=resolved.name[:120],
                        calories=resolved.calories,
                        variant_id=resolved.variant_id,
                        quantity=resolved.portion_g,
                        unit=resolved.unit,
                        protein_g_snapshot=resolved.protein_g,
                        carbs_g_snapshot=resolved.carbs_g,
                        fat_g_snapshot=resolved.fat_g,
                        created_at=now,
                    )
                    session.add(entry)
                    entries.append(entry)
                await session.flush()

                job.status = "completed"
                job.items = resolved_items
                job.entry_ids = [entry.id for entry in entries]
                job.error = None
                job.image_path = None
                job.updated_at = now
                job.completed_at = now
                await session.commit()
    except PhotoAnalysisError as exc:
        await _mark_failed(job_id, str(exc))
    except HTTPException as exc:
        detail = exc.detail
        message = (
            detail.get("message")
            if isinstance(detail, dict)
            else "This day cannot be edited."
        )
        await _mark_failed(job_id, str(message))
    except FileNotFoundError:
        await _mark_failed(job_id, "The meal photo was not available.")
    except Exception:
        logger.exception("Photo meal analysis failed for job %s", job_id)
        await _mark_failed(
            job_id, "Photo analysis failed. Take another photo and try again."
        )
    finally:
        await asyncio.to_thread(image_path.unlink, missing_ok=True)


async def recover_interrupted_photo_jobs() -> None:
    async with SessionLocal() as session:
        jobs = (
            (
                await session.execute(
                    select(PhotoMealJob).where(
                        PhotoMealJob.status.in_(["pending", "processing"])
                    )
                )
            )
            .scalars()
            .all()
        )
        for job in jobs:
            if job.image_path:
                await asyncio.to_thread(
                    Path(job.image_path).unlink, missing_ok=True
                )
            job.status = "failed"
            job.error = "Analysis was interrupted. Take the photo again."
            job.image_path = None
            job.updated_at = utc_now()
            job.completed_at = utc_now()
        if jobs:
            await session.commit()
