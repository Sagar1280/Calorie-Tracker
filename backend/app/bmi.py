from dataclasses import dataclass
from typing import Literal

Tone = Literal["green", "orange", "red"]


@dataclass(frozen=True)
class BmiResult:
    bmi: float
    category: str
    tone: Tone
    healthy_weight_min_kg: float
    healthy_weight_max_kg: float


def calculate_bmi(weight_kg: float, height_cm: float) -> BmiResult:
    height_m = height_cm / 100
    raw_bmi = weight_kg / (height_m * height_m)

    if raw_bmi < 18.5:
        category, tone = "Underweight", "orange"
    elif raw_bmi < 25:
        category, tone = "Healthy", "green"
    elif raw_bmi < 30:
        category, tone = "Overweight", "orange"
    else:
        category, tone = "Obese", "red"

    return BmiResult(
        bmi=round(raw_bmi, 1),
        category=category,
        tone=tone,
        healthy_weight_min_kg=round(18.5 * height_m * height_m, 1),
        healthy_weight_max_kg=round(24.9 * height_m * height_m, 1),
    )
