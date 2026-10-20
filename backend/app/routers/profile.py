from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from ..auth import get_current_user
from ..concurrency import write_lock
from ..db import SessionLocal
from ..models import Profile, User, utc_now
from ..schemas import ProfileEnvelope, ProfileIn, ProfileOut
from ..serializers import serialize_profile

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("", response_model=ProfileEnvelope)
async def get_profile(
    user: User = Depends(get_current_user),
) -> ProfileEnvelope:
    async with SessionLocal() as session:
        profile = (
            await session.execute(select(Profile).where(Profile.user_id == user.id))
        ).scalar_one_or_none()
        return ProfileEnvelope(
            profile=serialize_profile(profile) if profile else None
        )


@router.put("", response_model=ProfileOut)
async def upsert_profile(
    payload: ProfileIn, user: User = Depends(get_current_user)
) -> ProfileOut:
    async with write_lock:
        async with SessionLocal() as session:
            async with session.begin():
                profile = (
                    await session.execute(
                        select(Profile)
                        .where(Profile.user_id == user.id)
                        .with_for_update()
                    )
                ).scalar_one_or_none()

                if profile is None:
                    if payload.version != 0:
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "code": "version_conflict",
                                "message": "Profile does not exist yet; version must be 0.",
                                "current": None,
                            },
                        )
                    profile = Profile(
                        user_id=user.id,
                        version=1,
                        created_at=utc_now(),
                        updated_at=utc_now(),
                    )
                    session.add(profile)
                else:
                    if payload.version != profile.version:
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "code": "version_conflict",
                                "message": "This profile was changed elsewhere.",
                                "current": serialize_profile(profile).model_dump(
                                    mode="json"
                                ),
                            },
                        )
                    profile.version += 1
                    profile.updated_at = utc_now()

                profile.name = payload.name
                profile.age = payload.age
                profile.sex = payload.sex
                profile.height_cm = payload.height_cm
                profile.weight_kg = payload.weight_kg
                profile.activity_level = payload.activity_level

            return serialize_profile(profile)
