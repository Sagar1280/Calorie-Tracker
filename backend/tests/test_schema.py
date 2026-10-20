import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import SYNC_DATABASE_URL, Base, run_migrations
from app.models import (
    Brand,
    Food,
    FoodBarcode,
    FoodTag,
    FoodVariant,
    Recipe,
    RecipeItem,
    Tag,
    User,
)
from app.seed import DEFAULT_TAGS

EXPECTED_TABLES = {
    "users",
    "auth_sessions",
    "profiles",
    "brands",
    "foods",
    "food_variants",
    "food_aliases",
    "tags",
    "food_tags",
    "food_barcodes",
    "servings",
    "recipes",
    "recipe_items",
    "barcode_scans",
    "calorie_entries",
    "day_logs",
}


@pytest.fixture(scope="session", autouse=True)
def prepared_db():
    run_migrations()
    engine = create_engine(SYNC_DATABASE_URL)
    with Session(engine) as session:
        existing = set(session.execute(select(Tag.key)).scalars().all())
        for item in DEFAULT_TAGS:
            if item["key"] not in existing:
                session.add(Tag(**item))
        session.commit()
    engine.dispose()


@pytest.fixture()
def session():
    engine = create_engine(SYNC_DATABASE_URL)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_metadata_has_all_tables():
    assert EXPECTED_TABLES <= set(Base.metadata.tables)


def test_default_tags_seeded(session):
    keys = set(session.execute(select(Tag.key)).scalars().all())
    assert {"iron", "zinc", "vitamin_b12", "omega_3"} <= keys


def test_food_graph_round_trip(session):
    user = User(username="tester", password_hash="not-a-real-hash", role="admin")
    brand = Brand(name="Britannia Test", slug="britannia-test")
    session.add_all([user, brand])
    session.flush()

    food = Food(
        slug="britannia-good-day-cashew-test",
        name="Britannia Good Day Cashew Test",
        name_normalized="britannia good day cashew test",
        category="packaged",
        base_unit="g",
        source="curated",
        status="approved",
        is_verified=True,
        brand_id=brand.id,
    )
    session.add(food)
    session.flush()

    variant = FoodVariant(
        food_id=food.id,
        state="as_sold",
        label="",
        kcal=500,
        protein_g=6.0,
        carbs_g=62.0,
        fat_g=25.0,
        base_amount=100,
        base_unit="g",
        is_default=True,
    )
    session.add(variant)
    session.flush()

    barcode = FoodBarcode(
        food_id=food.id,
        variant_id=variant.id,
        barcode="8901063099999",
        pack_amount=100,
        pack_unit="g",
        source="curated",
    )
    recipe = Recipe(
        slug="dal-rice-test",
        name="Dal Rice",
        servings=2,
        status="approved",
    )
    session.add_all([barcode, recipe])
    session.flush()

    recipe_item = RecipeItem(
        recipe_id=recipe.id,
        variant_id=variant.id,
        quantity=200,
        unit="g",
        position=0,
    )
    session.add(recipe_item)

    iron = session.execute(select(Tag).where(Tag.key == "iron")).scalar_one()
    session.add(FoodTag(food_id=food.id, tag_id=iron.id))
    session.commit()

    stored = session.execute(
        select(FoodVariant).where(FoodVariant.food_id == food.id)
    ).scalar_one()
    assert stored.kcal == 500
    assert barcode.id is not None
    assert recipe_item.id is not None
    stored_barcode = session.execute(
        select(FoodBarcode).where(FoodBarcode.food_id == food.id)
    ).scalar_one()
    assert stored_barcode.barcode == "8901063099999"
