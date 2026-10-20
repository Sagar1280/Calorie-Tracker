from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(username) BETWEEN 3 AND 32", name="ck_users_username"),
        CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="user", server_default="user"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("age BETWEEN 2 AND 120", name="ck_profiles_age"),
        CheckConstraint("sex IN ('male', 'female', 'other')", name="ck_profiles_sex"),
        CheckConstraint(
            "activity_level IN ('sedentary', 'light', 'moderate', 'active', 'very_active')",
            name="ck_profiles_activity_level",
        ),
        CheckConstraint("height_cm BETWEEN 50 AND 260", name="ck_profiles_height"),
        CheckConstraint("weight_kg BETWEEN 10 AND 500", name="ck_profiles_weight"),
        CheckConstraint("version >= 1", name="ck_profiles_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    sex: Mapped[str] = mapped_column(String(16), nullable=False)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    activity_level: Mapped[str] = mapped_column(
        String(24), nullable=False, default="moderate"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class Brand(Base):
    __tablename__ = "brands"
    __table_args__ = (UniqueConstraint("slug", name="uq_brands_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    foods: Mapped[list[Food]] = relationship(back_populates="brand")


class Food(Base):
    __tablename__ = "foods"
    __table_args__ = (
        CheckConstraint("base_unit IN ('g', 'ml')", name="ck_foods_base_unit"),
        CheckConstraint(
            "source IN ('curated', 'off', 'user')", name="ck_foods_source"
        ),
        CheckConstraint(
            "status IN ('approved', 'pending', 'rejected', 'private')",
            name="ck_foods_status",
        ),
        UniqueConstraint("slug", name="uq_foods_slug"),
        Index("ix_foods_status_category", "status", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(48), nullable=True)
    brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("brands.id", ondelete="SET NULL"), nullable=True, index=True
    )
    base_unit: Mapped[str] = mapped_column(String(4), nullable=False, default="g")
    region: Mapped[str | None] = mapped_column(String(24), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="curated"
    )
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="approved", server_default="approved"
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    brand: Mapped[Brand | None] = relationship(
        back_populates="foods", lazy="selectin"
    )
    variants: Mapped[list[FoodVariant]] = relationship(
        back_populates="food",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="FoodVariant.id",
    )
    aliases: Mapped[list[FoodAlias]] = relationship(
        back_populates="food",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="FoodAlias.alias_normalized",
    )
    tags: Mapped[list[Tag]] = relationship(
        secondary="food_tags", lazy="selectin", order_by="Tag.key"
    )
    barcodes: Mapped[list[FoodBarcode]] = relationship(
        back_populates="food",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="FoodBarcode.barcode",
    )


class FoodVariant(Base):
    __tablename__ = "food_variants"
    __table_args__ = (
        CheckConstraint(
            "state IN ('raw', 'cooked', 'as_sold')", name="ck_food_variants_state"
        ),
        CheckConstraint("base_unit IN ('g', 'ml')", name="ck_food_variants_base_unit"),
        UniqueConstraint(
            "food_id", "state", "label", name="uq_food_variants_food_state_label"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    food_id: Mapped[int] = mapped_column(
        ForeignKey("foods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="as_sold")
    label: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    kcal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protein_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    carbs_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_amount: Mapped[float] = mapped_column(Float, nullable=False, default=100)
    base_unit: Mapped[str] = mapped_column(String(4), nullable=False, default="g")
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    food: Mapped[Food] = relationship(back_populates="variants")
    servings: Mapped[list[Serving]] = relationship(
        back_populates="variant",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Serving.id",
    )


class FoodAlias(Base):
    __tablename__ = "food_aliases"
    __table_args__ = (
        UniqueConstraint(
            "food_id", "alias_normalized", name="uq_food_aliases_food_alias"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    food_id: Mapped[int] = mapped_column(
        ForeignKey("foods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(160), nullable=False)
    alias_normalized: Mapped[str] = mapped_column(
        String(160), nullable=False, index=True
    )
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")

    food: Mapped[Food] = relationship(back_populates="aliases")


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        CheckConstraint(
            "type IN ('micronutrient', 'diet', 'cuisine')", name="ck_tags_type"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="micronutrient"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FoodTag(Base):
    __tablename__ = "food_tags"

    food_id: Mapped[int] = mapped_column(
        ForeignKey("foods.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class FoodBarcode(Base):
    __tablename__ = "food_barcodes"
    __table_args__ = (
        CheckConstraint(
            "pack_unit IS NULL OR pack_unit IN ('g', 'ml')",
            name="ck_food_barcodes_pack_unit",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    food_id: Mapped[int] = mapped_column(
        ForeignKey("foods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("food_variants.id", ondelete="SET NULL"), nullable=True
    )
    barcode: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    pack_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    pack_unit: Mapped[str | None] = mapped_column(String(4), nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="curated")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    food: Mapped[Food] = relationship(back_populates="barcodes")
    variant: Mapped[FoodVariant | None] = relationship()


class Serving(Base):
    __tablename__ = "servings"
    __table_args__ = (
        CheckConstraint("unit IN ('g', 'ml')", name="ck_servings_unit"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("food_variants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(40), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(4), nullable=False)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    variant: Mapped[FoodVariant] = relationship(back_populates="servings")


class Recipe(Base):
    __tablename__ = "recipes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('approved', 'pending', 'rejected', 'private')",
            name="ck_recipes_status",
        ),
        CheckConstraint("servings > 0", name="ck_recipes_servings"),
        UniqueConstraint("slug", name="uq_recipes_slug"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    servings: Mapped[float] = mapped_column(Float, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="private", server_default="private"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    items: Mapped[list[RecipeItem]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="RecipeItem.position",
    )


class RecipeItem(Base):
    __tablename__ = "recipe_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_recipe_items_quantity"),
        CheckConstraint("unit IN ('g', 'ml')", name="ck_recipe_items_unit"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("food_variants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(4), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    recipe: Mapped[Recipe] = relationship(back_populates="items")
    variant: Mapped[FoodVariant] = relationship()


class BarcodeScan(Base):
    __tablename__ = "barcode_scans"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'resolved', 'rejected')",
            name="ck_barcode_scans_status",
        ),
        Index("ix_barcode_scans_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    matched_food_id: Mapped[int | None] = mapped_column(
        ForeignKey("foods.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FoodReview(Base):
    __tablename__ = "food_reviews"
    __table_args__ = (
        CheckConstraint(
            "action IN ('updated', 'approved', 'rejected')",
            name="ck_food_reviews_action",
        ),
        CheckConstraint(
            "status IN ('approved', 'pending', 'rejected', 'private')",
            name="ck_food_reviews_status",
        ),
        Index("ix_food_reviews_food_created", "food_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    food_id: Mapped[int] = mapped_column(
        ForeignKey("foods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    reviewer: Mapped[User | None] = relationship()


class CalorieEntry(Base):
    __tablename__ = "calorie_entries"
    __table_args__ = (
        CheckConstraint(
            "calories IS NULL OR calories BETWEEN 0 AND 10000",
            name="ck_calorie_entries_calories",
        ),
        CheckConstraint(
            "meal IN ('breakfast', 'lunch', 'dinner', 'snack')",
            name="ck_calorie_entries_meal",
        ),
        CheckConstraint(
            "name IS NULL OR length(name) BETWEEN 1 AND 120",
            name="ck_calorie_entries_name",
        ),
        CheckConstraint(
            "unit IS NULL OR unit IN ('g', 'ml')", name="ck_calorie_entries_unit"
        ),
        Index("ix_calorie_entries_user_date", "user_id", "entry_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("food_variants.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(4), nullable=True)
    protein_g_snapshot: Mapped[float | None] = mapped_column(Float, nullable=True)
    carbs_g_snapshot: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_g_snapshot: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class DayLog(Base):
    __tablename__ = "day_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "log_date", name="uq_day_logs_user_date"),
        Index("ix_day_logs_user_date", "user_id", "log_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
