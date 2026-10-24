from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Sex = Literal["male", "female", "other"]
ActivityLevel = Literal["sedentary", "light", "moderate", "active", "very_active"]
Tone = Literal["green", "orange", "red"]
Meal = Literal["breakfast", "lunch", "dinner", "snack"]
GoalSource = Literal["profile", "default"]
UsernamePattern = r"^[a-z0-9._-]+$"


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=32, pattern=UsernamePattern)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower() if isinstance(value, str) else value


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower() if isinstance(value, str) else value


class UserOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    username: str
    role: Literal["user", "admin"] = "user"
    created_at: datetime


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    age: int = Field(ge=2, le=120)
    sex: Sex
    height_cm: float = Field(gt=50, le=260)
    weight_kg: float = Field(gt=10, le=500)
    activity_level: ActivityLevel = "moderate"
    version: int = Field(default=0, ge=0)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Name cannot be blank")
        return value

    @field_validator("height_cm", "weight_kg")
    @classmethod
    def round_measurement(cls, value: float) -> float:
        return round(value, 1)


class ProfileOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    age: int
    sex: Sex
    height_cm: float
    weight_kg: float
    activity_level: ActivityLevel
    version: int
    bmi: float
    category: str
    tone: Tone
    healthy_weight_min_kg: float
    healthy_weight_max_kg: float
    created_at: datetime
    updated_at: datetime


class ProfileEnvelope(BaseModel):
    profile: ProfileOut | None


class CalorieEntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    meal: Meal
    name: str | None = Field(default=None, max_length=120)
    calories: int | None = Field(default=None, ge=0, le=10000)
    variant_id: int | None = Field(default=None, gt=0)
    quantity: float | None = Field(default=None, gt=0, le=10000)
    unit: Literal["g", "ml", "pack"] | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        return value or None


class CalorieEntryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    date: date
    meal: Meal
    name: str | None
    calories: int | None
    variant_id: int | None
    quantity: float | None
    unit: Literal["g", "ml"] | None
    protein_g: float | None = None
    fat_g: float | None = None
    created_at: datetime


class DayLogOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    goal: int
    goal_source: GoalSource
    consumed: int
    remaining: int
    done: bool
    protein_goal_g: int
    fat_goal_g: int
    water_goal_ml: int
    protein_consumed_g: float
    fat_consumed_g: float
    entries: list[CalorieEntryOut]


class DayDoneIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    done: bool


class MonthDayOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    consumed: int
    entries: int
    done: bool


class MonthLogOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int
    month: int
    goal: int
    goal_source: GoalSource
    days: list[MonthDayOut]
    total_consumed: int
    days_logged: int
    average_consumed: float
    days_over_goal: int


class TagOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    type: str


class BrandOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    slug: str


class ServingOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    label: str
    amount: float
    unit: str
    is_default: bool


class VariantOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    state: str
    label: str
    kcal: int | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    base_amount: float
    base_unit: str
    is_default: bool
    servings: list[ServingOut] = []


class BarcodeLookupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    barcode: str = Field(min_length=8, max_length=14, pattern=r"^\d+$")

    @field_validator("barcode", mode="before")
    @classmethod
    def clean_barcode(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        return "".join(value.split()).replace("-", "")


class BarcodeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    barcode: str
    pack_amount: float | None
    pack_unit: str | None
    source: str
    variant_id: int | None


class FoodSummaryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    slug: str
    name: str
    category: str
    subcategory: str | None
    brand: BrandOut | None
    base_unit: str
    region: str | None
    source: str
    status: str
    is_verified: bool
    tags: list[TagOut]
    default_variant: VariantOut | None


class FoodDetailOut(FoodSummaryOut):
    description: str | None
    variants: list[VariantOut]
    aliases: list[str]
    barcodes: list[BarcodeOut]


class BarcodeScanOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    barcode: str
    status: Literal["database", "review", "queued"]
    food: FoodDetailOut


class FoodListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FoodSummaryOut]
    total: int
    limit: int
    offset: int


class AdminVariantUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kcal: int = Field(ge=0, le=10000)
    protein_g: float = Field(ge=0, le=1000)
    carbs_g: float = Field(ge=0, le=1000)
    fat_g: float = Field(ge=0, le=1000)
    base_amount: float = Field(gt=0, le=10000)
    base_unit: Literal["g", "ml"]


class AdminFoodReviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    action: Literal["updated", "approved", "rejected"]
    status: str
    is_verified: bool
    note: str | None
    reviewer_username: str | None
    created_at: datetime


class AdminFoodReviewListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AdminFoodReviewOut]


class AdminFoodUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=32)
    subcategory: str | None = Field(default=None, max_length=48)
    brand_name: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    status: Literal["approved", "pending", "rejected", "private"]
    is_verified: bool
    review_note: str | None = Field(default=None, max_length=1000)
    variant: AdminVariantUpdateIn

    @field_validator("name", "category")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Value cannot be blank")
        return value

    @field_validator("subcategory", "brand_name", "description", "review_note")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        return value or None


class AdminFoodCreateIn(AdminFoodUpdateIn):
    pass


class AdminBulkActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[int] = Field(min_length=1, max_length=100)
    action: Literal["approve", "reject", "delete"]
    review_note: str | None = Field(default=None, max_length=1000)


class AdminBulkResultOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "reject", "delete"]
    food_ids: list[int]
    affected: int


class PhotoMealItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    portion_g: float
    calories: int
    protein_g: float
    carbs_g: float = 0
    fat_g: float
    confidence: float
    matched: bool = False
    food_id: int | None = None


class PhotoMealJobOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    date: date
    meal: Meal
    status: Literal["pending", "processing", "completed", "failed"]
    items: list[PhotoMealItemOut]
    entry_ids: list[int]
    error: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class PhotoMealConfigOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    model: str
