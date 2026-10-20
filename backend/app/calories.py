from dataclasses import dataclass
from typing import Literal

from .models import Profile

GoalSource = Literal["profile", "default"]

DEFAULT_DAILY_GOAL = 2000
MIN_DAILY_GOAL = 1200
MAX_DAILY_GOAL = 6000

_ACTIVITY_FACTORS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

_SEX_OFFSETS = {
    "male": 5.0,
    "female": -161.0,
    "other": -78.0,
}

_PROTEIN_G_PER_KG = {
    "sedentary": 0.9,
    "light": 1.0,
    "moderate": 1.1,
    "active": 1.3,
    "very_active": 1.5,
}

def _water_ml_per_kg(bmi: float) -> int:
    if bmi < 18.5:
        return 40
    if bmi < 25:
        return 35
    if bmi < 30:
        return 33
    return 30


@dataclass(frozen=True)
class NutritionTargets:
    protein_g: int
    fat_g: int
    water_ml: int


def daily_calorie_goal(profile: Profile | None) -> tuple[int, GoalSource]:
    """Estimate a maintenance calorie goal from the user's profile.

    Falls back to a sensible default when the user has not created a profile.
    Uses the Mifflin-St Jeor equation scaled by an activity factor.
    """
    if profile is None:
        return DEFAULT_DAILY_GOAL, "default"

    offset = _SEX_OFFSETS.get(profile.sex, _SEX_OFFSETS["other"])
    bmr = (
        10.0 * profile.weight_kg
        + 6.25 * profile.height_cm
        - 5.0 * profile.age
        + offset
    )
    factor = _ACTIVITY_FACTORS.get(profile.activity_level, 1.55)
    goal = int(round((bmr * factor) / 10.0) * 10)
    goal = max(MIN_DAILY_GOAL, min(goal, MAX_DAILY_GOAL))
    return goal, "profile"


def daily_nutrition_targets(
    profile: Profile | None, calorie_goal: int
) -> NutritionTargets:
    if profile is None:
        return NutritionTargets(
            protein_g=60,
            fat_g=max(30, round(calorie_goal * 0.25 / 9)),
            water_ml=2000,
        )

    activity = profile.activity_level
    protein = round(profile.weight_kg * _PROTEIN_G_PER_KG.get(activity, 1.1))
    fat = round(calorie_goal * 0.25 / 9)
    height_m = max(profile.height_cm, 1) / 100
    bmi = profile.weight_kg / (height_m * height_m)
    water = round(profile.weight_kg * _water_ml_per_kg(bmi) / 50) * 50
    return NutritionTargets(
        protein_g=max(20, protein),
        fat_g=max(30, fat),
        water_ml=max(1500, min(water, 5000)),
    )
