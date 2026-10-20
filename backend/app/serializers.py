from datetime import datetime, timezone

from .bmi import calculate_bmi
from .models import Profile, User
from .schemas import ProfileOut, UserOut


def with_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def to_user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        role=user.role,
        created_at=with_utc(user.created_at),
    )


def serialize_profile(profile: Profile) -> ProfileOut:
    result = calculate_bmi(profile.weight_kg, profile.height_cm)
    return ProfileOut(
        id=profile.id,
        name=profile.name,
        age=profile.age,
        sex=profile.sex,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        activity_level=profile.activity_level,
        version=profile.version,
        bmi=result.bmi,
        category=result.category,
        tone=result.tone,
        healthy_weight_min_kg=result.healthy_weight_min_kg,
        healthy_weight_max_kg=result.healthy_weight_max_kg,
        created_at=with_utc(profile.created_at),
        updated_at=with_utc(profile.updated_at),
    )
