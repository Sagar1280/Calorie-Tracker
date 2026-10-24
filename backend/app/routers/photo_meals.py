import asyncio
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from sqlalchemy import select

from ..auth import get_current_user
from ..config import (
    PHOTO_ANALYSIS_ENABLED,
    PHOTO_LLM_MODEL,
    PHOTO_MAX_IMAGE_BYTES,
    PHOTO_UPLOAD_DIR,
)
from ..db import SessionLocal
from ..limiter import enforce_rate_limit
from ..models import PhotoMealJob, User, utc_now
from ..schemas import Meal, PhotoMealConfigOut, PhotoMealJobOut
from ..serializers import to_photo_job_out
from ..services.calories import ensure_day_editable
from ..services.photo_meals import process_photo_job

router = APIRouter(prefix="/api/photo-meals", tags=["photo-meals"])


def _image_type(data: bytes) -> tuple[str, str] | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


@router.get("/config", response_model=PhotoMealConfigOut)
async def photo_config(
    _user: User = Depends(get_current_user),
) -> PhotoMealConfigOut:
    return PhotoMealConfigOut(
        enabled=PHOTO_ANALYSIS_ENABLED,
        model=PHOTO_LLM_MODEL if PHOTO_ANALYSIS_ENABLED else "",
    )


@router.get("", response_model=list[PhotoMealJobOut])
async def list_photo_jobs(
    limit: int = Query(default=10, ge=1, le=30),
    user: User = Depends(get_current_user),
) -> list[PhotoMealJobOut]:
    async with SessionLocal() as session:
        jobs = (
            (
                await session.execute(
                    select(PhotoMealJob)
                    .where(PhotoMealJob.user_id == user.id)
                    .order_by(PhotoMealJob.created_at.desc(), PhotoMealJob.id.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [to_photo_job_out(job) for job in jobs]


@router.get("/{job_id}", response_model=PhotoMealJobOut)
async def get_photo_job(
    job_id: int, user: User = Depends(get_current_user)
) -> PhotoMealJobOut:
    async with SessionLocal() as session:
        job = (
            await session.execute(
                select(PhotoMealJob).where(
                    PhotoMealJob.id == job_id,
                    PhotoMealJob.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if job is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "photo_job_not_found",
                    "message": "That photo analysis was not found.",
                },
            )
        return to_photo_job_out(job)


@router.post("/analyze", response_model=PhotoMealJobOut, status_code=202)
async def analyze_photo(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...),
    meal: Meal = Form(...),
    target_date: date = Form(..., alias="date"),
    user: User = Depends(get_current_user),
) -> PhotoMealJobOut:
    if not PHOTO_ANALYSIS_ENABLED:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "photo_analysis_disabled",
                "message": "Photo analysis is not configured on this server.",
            },
        )

    enforce_rate_limit(
        "photo-analysis",
        str(user.id),
        limit=6,
        window_seconds=600,
        message="Too many photo analyses. Wait a few minutes and try again.",
    )

    async with SessionLocal() as session:
        await ensure_day_editable(session, user.id, target_date)

    data = await image.read(PHOTO_MAX_IMAGE_BYTES + 1)
    await image.close()
    if len(data) > PHOTO_MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "photo_too_large",
                "message": "That photo is too large. Use an image under 8 MB.",
            },
        )

    detected = _image_type(data)
    if detected is None:
        raise HTTPException(
            status_code=415,
            detail={
                "code": "unsupported_image",
                "message": "Use a JPEG, PNG, or WebP photo.",
            },
        )
    _mime_type, extension = detected

    upload_path = PHOTO_UPLOAD_DIR / f"{uuid4().hex}{extension}"
    await asyncio.to_thread(upload_path.write_bytes, data)

    try:
        async with SessionLocal() as session:
            job = PhotoMealJob(
                user_id=user.id,
                entry_date=target_date,
                meal=meal,
                status="pending",
                image_path=str(upload_path),
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            result = to_photo_job_out(job)
    except Exception:
        await asyncio.to_thread(Path(upload_path).unlink, missing_ok=True)
        raise

    background_tasks.add_task(process_photo_job, job.id)
    return result
