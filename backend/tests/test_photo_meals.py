import base64
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.db import SYNC_DATABASE_URL, run_migrations
from app.limiter import reset_rate_limits
from app.main import app
from app.models import (
    AuthSession,
    CalorieEntry,
    DayLog,
    Food,
    FoodAlias,
    FoodBarcode,
    FoodReview,
    FoodVariant,
    PhotoMealJob,
    Profile,
    User,
)
from app.photo_llm import MealPhotoItem

PNG_IMAGE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAusB9Y9ZlK0AAAAASUVORK5CYII="
)


@pytest.fixture(scope="module")
def client():
    reset_rate_limits()
    run_migrations()
    with TestClient(app) as test_client:
        yield test_client
    reset_rate_limits()


def _register(client: TestClient) -> tuple[int, str]:
    username = f"photo-test-{uuid.uuid4().hex[:10]}"
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "Photo-Test-9f3a!"},
    )
    assert response.status_code == 201
    return response.json()["id"], username


def _delete_user(user_id: int) -> None:
    engine = create_engine(SYNC_DATABASE_URL)
    with Session(engine) as session:
        food_ids = select(Food.id).where(Food.created_by_user_id == user_id)
        session.execute(delete(PhotoMealJob).where(PhotoMealJob.user_id == user_id))
        session.execute(delete(CalorieEntry).where(CalorieEntry.user_id == user_id))
        session.execute(
            delete(FoodAlias).where(FoodAlias.food_id.in_(food_ids))
        )
        session.execute(
            delete(FoodBarcode).where(FoodBarcode.food_id.in_(food_ids))
        )
        session.execute(
            delete(FoodReview).where(FoodReview.food_id.in_(food_ids))
        )
        session.execute(
            delete(FoodVariant).where(FoodVariant.food_id.in_(food_ids))
        )
        session.execute(delete(Food).where(Food.created_by_user_id == user_id))
        session.execute(delete(DayLog).where(DayLog.user_id == user_id))
        session.execute(delete(Profile).where(Profile.user_id == user_id))
        session.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
        session.execute(delete(User).where(User.id == user_id))
        session.commit()
    engine.dispose()


@pytest.fixture
def enabled_photo(client, monkeypatch, tmp_path):
    async def fake_analysis(image: bytes, mime_type: str) -> list[MealPhotoItem]:
        assert image.startswith(b"\x89PNG")
        assert mime_type == "image/png"
        return [
            MealPhotoItem(
                name="Dal",
                portion_g=150,
                calories=180,
                protein_g=9,
                fat_g=4,
                confidence=0.9,
            ),
            MealPhotoItem(
                name="Steamed rice",
                portion_g=200,
                calories=260,
                protein_g=5,
                fat_g=1,
                confidence=0.85,
            ),
            MealPhotoItem(
                name="Aloo fry",
                portion_g=100,
                calories=210,
                protein_g=2,
                fat_g=10,
                confidence=0.8,
            ),
        ]

    monkeypatch.setattr(
        "app.routers.photo_meals.PHOTO_ANALYSIS_ENABLED", True
    )
    monkeypatch.setattr(
        "app.routers.photo_meals.PHOTO_UPLOAD_DIR", tmp_path
    )
    monkeypatch.setattr(
        "app.services.photo_meals.analyze_meal_photo", fake_analysis
    )
    return tmp_path


def test_photo_analysis_persists_entries(client, enabled_photo):
    user_id, _ = _register(client)
    other_id = None
    day = date.today().isoformat()
    try:
        response = client.post(
            "/api/photo-meals/analyze",
            data={"meal": "lunch", "date": day},
            files={"image": ("meal.png", PNG_IMAGE, "image/png")},
        )
        assert response.status_code == 202
        job = response.json()
        assert job["status"] == "pending"
        assert job["meal"] == "lunch"

        completed = client.get(f"/api/photo-meals/{job['id']}")
        assert completed.status_code == 200
        body = completed.json()
        assert body["status"] == "completed"
        assert len(body["items"]) == 3
        assert len(body["entry_ids"]) == 3
        assert body["error"] is None

        day_log = client.get(f"/api/calories/day?date={day}").json()
        assert len(day_log["entries"]) == 3
        assert day_log["consumed"] == 650
        assert day_log["protein_consumed_g"] == 16
        assert day_log["fat_consumed_g"] == 15
        assert {entry["meal"] for entry in day_log["entries"]} == {"lunch"}
        assert {entry["name"] for entry in day_log["entries"]} == {
            "Dal",
            "Steamed rice",
            "Aloo fry",
        }

        listed = client.get("/api/photo-meals").json()
        assert listed[0]["id"] == job["id"]
        assert listed[0]["status"] == "completed"
        assert list(enabled_photo.iterdir()) == []

        assert client.post("/api/auth/logout").status_code == 204
        other_id, _ = _register(client)
        hidden = client.get(f"/api/photo-meals/{job['id']}")
        assert hidden.status_code == 404
    finally:
        if other_id is not None:
            _delete_user(other_id)
        _delete_user(user_id)


def test_photo_uses_database_values_and_queues_missing_food(
    client, enabled_photo, monkeypatch
):
    user_id, _ = _register(client)
    day = date.today().isoformat()
    engine = create_engine(SYNC_DATABASE_URL)
    try:
        with Session(engine) as session:
            food = Food(
                slug=f"photo-dal-match-{uuid.uuid4().hex[:8]}",
                name="Dal",
                name_normalized="dal",
                category="dal",
                base_unit="g",
                source="curated",
                status="approved",
                is_verified=True,
                created_by_user_id=user_id,
            )
            session.add(food)
            session.flush()
            variant = FoodVariant(
                food_id=food.id,
                state="cooked",
                label="",
                kcal=100,
                protein_g=5,
                carbs_g=10,
                fat_g=2,
                base_amount=100,
                base_unit="g",
                is_default=True,
            )
            session.add(variant)
            session.commit()
            food_id = food.id
            variant_id = variant.id

        async def fake_analysis(
            image: bytes, mime_type: str
        ) -> list[MealPhotoItem]:
            return [
                MealPhotoItem(
                    name="Dal",
                    portion_g=150,
                    calories=180,
                    protein_g=9,
                    carbs_g=18,
                    fat_g=4,
                    confidence=0.9,
                ),
                MealPhotoItem(
                    name="Mystery Curry",
                    portion_g=100,
                    calories=220,
                    protein_g=8,
                    carbs_g=20,
                    fat_g=12,
                    confidence=0.7,
                ),
            ]

        monkeypatch.setattr(
            "app.services.photo_meals.analyze_meal_photo", fake_analysis
        )

        response = client.post(
            "/api/photo-meals/analyze",
            data={"meal": "lunch", "date": day},
            files={"image": ("meal.png", PNG_IMAGE, "image/png")},
        )
        assert response.status_code == 202
        body = client.get(f"/api/photo-meals/{response.json()['id']}").json()
        assert body["status"] == "completed"
        assert body["items"][0]["matched"] is True
        assert body["items"][0]["food_id"] == food_id
        assert body["items"][0]["calories"] == 150
        assert body["items"][1]["matched"] is False

        day_log = client.get(f"/api/calories/day?date={day}").json()
        dal = next(item for item in day_log["entries"] if item["name"] == "Dal")
        assert dal["calories"] == 150
        assert dal["protein_g"] == 7.5
        assert dal["fat_g"] == 3.0
        assert dal["variant_id"] == variant_id

        with Session(engine) as session:
            draft = session.execute(
                select(Food).where(Food.name_normalized == "mystery curry")
            ).scalar_one()
            assert draft.status == "pending"
            assert draft.source == "user"
            assert draft.created_by_user_id == user_id
            draft_variant = session.execute(
                select(FoodVariant).where(FoodVariant.food_id == draft.id)
            ).scalar_one()
            assert draft_variant.base_amount == 100
            assert draft_variant.kcal == 220
            assert draft_variant.carbs_g == 20
    finally:
        engine.dispose()
        _delete_user(user_id)


def test_photo_analysis_validates_config_and_file(client, monkeypatch):
    user_id, _ = _register(client)
    day = date.today().isoformat()
    try:
        monkeypatch.setattr(
            "app.routers.photo_meals.PHOTO_ANALYSIS_ENABLED", False
        )
        disabled = client.post(
            "/api/photo-meals/analyze",
            data={"meal": "lunch", "date": day},
            files={"image": ("meal.png", PNG_IMAGE, "image/png")},
        )
        assert disabled.status_code == 503
        assert disabled.json()["detail"]["code"] == "photo_analysis_disabled"

        monkeypatch.setattr(
            "app.routers.photo_meals.PHOTO_ANALYSIS_ENABLED", True
        )
        invalid = client.post(
            "/api/photo-meals/analyze",
            data={"meal": "lunch", "date": day},
            files={"image": ("meal.txt", b"not an image", "text/plain")},
        )
        assert invalid.status_code == 415
        assert invalid.json()["detail"]["code"] == "unsupported_image"
    finally:
        _delete_user(user_id)
