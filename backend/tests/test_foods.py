import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.calories import daily_nutrition_targets
from app.db import SYNC_DATABASE_URL, run_migrations
from app.limiter import reset_rate_limits
from app.main import app
from app.models import (
    Brand,
    Food,
    FoodAlias,
    FoodBarcode,
    FoodVariant,
    Profile,
    Serving,
    Tag,
    User,
)
from app.openfoodfacts import OffProduct
from app.seed import DEFAULT_TAGS


@pytest.fixture(scope="module")
def client():
    reset_rate_limits()
    run_migrations()
    engine = create_engine(SYNC_DATABASE_URL)
    with Session(engine) as session:
        existing_tags = set(session.execute(select(Tag.key)).scalars().all())
        for item in DEFAULT_TAGS:
            if item["key"] not in existing_tags:
                session.add(Tag(**item))
        user = User(username="food-tester", password_hash="x", role="user")
        session.add(user)
        session.flush()

        brand = Brand(name="Britannia", slug="britannia")
        session.add(brand)
        session.flush()

        packaged = Food(
            slug="britannia-good-day-cashew",
            name="Britannia Good Day Cashew",
            name_normalized="britannia good day cashew",
            category="packaged",
            base_unit="g",
            source="curated",
            status="approved",
            brand_id=brand.id,
        )
        session.add(packaged)
        session.flush()

        variant = FoodVariant(
            food_id=packaged.id,
            state="as_sold",
            label="",
            kcal=500,
            protein_g=6,
            carbs_g=62,
            fat_g=25,
            base_amount=100,
            base_unit="g",
            is_default=True,
        )
        session.add(variant)
        session.flush()

        session.add_all(
            [
                FoodAlias(
                    food_id=packaged.id,
                    alias="good day cashew",
                    alias_normalized="good day cashew",
                ),
                FoodBarcode(
                    food_id=packaged.id,
                    variant_id=variant.id,
                    barcode="8901063012345",
                    pack_amount=100,
                    pack_unit="g",
                    source="curated",
                ),
                Serving(
                    variant_id=variant.id,
                    label="1 pack",
                    amount=50,
                    unit="g",
                    is_default=True,
                ),
            ]
        )

        dal = Food(
            slug="dal-tadka",
            name="Dal tadka",
            name_normalized="dal tadka",
            category="dal",
            base_unit="g",
            source="curated",
            status="approved",
        )
        session.add(dal)
        session.flush()
        session.add(
            FoodVariant(
                food_id=dal.id,
                state="cooked",
                label="",
                kcal=130,
                protein_g=6,
                carbs_g=18,
                fat_g=4,
                base_amount=100,
                base_unit="g",
                is_default=True,
            )
        )

        off_food = Food(
            slug="acme-review-bar-off-1234567890123",
            name="Acme Review Bar",
            name_normalized="acme review bar",
            category="packaged",
            base_unit="g",
            source="off",
            status="approved",
            is_verified=False,
        )
        session.add(off_food)
        session.flush()
        off_variant = FoodVariant(
            food_id=off_food.id,
            state="as_sold",
            label="",
            kcal=200,
            protein_g=5,
            carbs_g=30,
            fat_g=7,
            base_amount=100,
            base_unit="g",
            is_default=True,
        )
        session.add(off_variant)
        session.flush()
        session.add(
            FoodBarcode(
                food_id=off_food.id,
                variant_id=off_variant.id,
                barcode="1234567890123",
                pack_amount=50,
                pack_unit="g",
                source="off",
            )
        )
        session.commit()
        ids = {
            "packaged_id": packaged.id,
            "packaged_variant_id": variant.id,
            "dal_id": dal.id,
            "off_food_id": off_food.id,
            "off_variant_id": off_variant.id,
            "user_id": user.id,
        }
    engine.dispose()

    current_user = User(
        id=ids["user_id"], username="food-tester", password_hash="x", role="user"
    )
    app.dependency_overrides[get_current_user] = lambda: current_user
    with TestClient(app) as test_client:
        yield test_client, ids
    reset_rate_limits()
    app.dependency_overrides.clear()


def test_search_by_name(client):
    test_client, _ = client
    response = test_client.get("/api/foods", params={"q": "dal"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert any(item["slug"] == "dal-tadka" for item in body["items"])


def test_search_by_alias(client):
    test_client, _ = client
    response = test_client.get("/api/foods", params={"q": "good day"})
    assert response.status_code == 200
    assert any(
        item["slug"] == "britannia-good-day-cashew"
        for item in response.json()["items"]
    )


def test_search_filters_by_category(client):
    test_client, _ = client
    response = test_client.get("/api/foods", params={"category": "dal"})
    assert response.status_code == 200
    slugs = [item["slug"] for item in response.json()["items"]]
    assert "dal-tadka" in slugs
    assert "britannia-good-day-cashew" not in slugs


def test_food_detail_includes_variant_and_barcode(client):
    test_client, ids = client
    response = test_client.get(f"/api/foods/{ids['packaged_id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "britannia-good-day-cashew"
    assert body["brand"]["slug"] == "britannia"
    assert len(body["variants"]) == 1
    assert body["default_variant"]["kcal"] == 500
    assert body["barcodes"][0]["barcode"] == "8901063012345"
    assert "good day cashew" in body["aliases"]


def test_barcode_lookup(client):
    test_client, _ = client
    response = test_client.get("/api/foods/barcode/8901063012345")
    assert response.status_code == 200
    assert response.json()["slug"] == "britannia-good-day-cashew"


def test_barcode_lookup_missing(client):
    test_client, _ = client
    response = test_client.get("/api/foods/barcode/0000000000000")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "barcode_not_found"


def test_barcode_scan_rejects_invalid_barcode(client):
    test_client, _ = client
    response = test_client.post(
        "/api/foods/barcode/scan",
        json={"barcode": "1234"},
    )
    assert response.status_code == 422


def test_barcode_resolve_endpoint_removed(client):
    test_client, _ = client
    response = test_client.post(
        "/api/foods/barcode/resolve",
        json={"barcode": "8901063012345"},
    )
    assert response.status_code == 405


def test_barcode_scan_prefers_local_database(client, monkeypatch):
    test_client, _ = client

    async def unexpected_lookup(barcode):
        raise AssertionError(f"remote lookup used for local barcode {barcode}")

    monkeypatch.setattr("app.foods.lookup_off_product", unexpected_lookup)
    response = test_client.post(
        "/api/foods/barcode/scan",
        json={"barcode": "8901063012345"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "database"
    assert body["food"]["slug"] == "britannia-good-day-cashew"


def test_barcode_scan_queues_openfoodfacts_import_for_review(
    client, monkeypatch
):
    test_client, _ = client

    async def fake_lookup(barcode):
        return OffProduct(
            barcode=barcode,
            name="Acme Oat Bites",
            brand="Acme",
            kcal=410,
            protein_g=8,
            carbs_g=61,
            fat_g=14,
            pack_amount=120,
            pack_unit="g",
        )

    monkeypatch.setattr("app.foods.lookup_off_product", fake_lookup)
    response = test_client.post(
        "/api/foods/barcode/scan",
        json={"barcode": "5555555555555"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "review"
    assert body["food"]["status"] == "pending"
    assert body["food"]["is_verified"] is False
    assert body["food"]["source"] == "off"
    assert body["food"]["barcodes"][0]["barcode"] == "5555555555555"

    cached = test_client.post(
        "/api/foods/barcode/scan",
        json={"barcode": "5555555555555"},
    )
    assert cached.status_code == 200
    assert cached.json()["status"] == "review"
    assert cached.json()["food"]["id"] == body["food"]["id"]


def test_barcode_scan_queues_unknown_barcode_for_review(client, monkeypatch):
    test_client, _ = client

    async def fake_lookup(barcode):
        return None

    monkeypatch.setattr("app.foods.lookup_off_product", fake_lookup)
    response = test_client.post(
        "/api/foods/barcode/scan",
        json={"barcode": "6666666666666"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["food"]["name"] == "Barcode 6666666666666"
    assert body["food"]["status"] == "pending"
    assert body["food"]["source"] == "user"
    assert body["food"]["barcodes"][0]["barcode"] == "6666666666666"


def test_food_detail_missing(client):
    test_client, _ = client
    response = test_client.get("/api/foods/999999")
    assert response.status_code == 404


def test_tags_endpoint(client):
    test_client, _ = client
    response = test_client.get("/api/tags")
    assert response.status_code == 200
    keys = {tag["key"] for tag in response.json()}
    assert {"iron", "calcium", "omega_3"} <= keys


def test_add_entry_from_variant_by_weight(client):
    test_client, ids = client
    response = test_client.post(
        "/api/calories/entries",
        json={
            "date": "2026-10-20",
            "meal": "snack",
            "variant_id": ids["packaged_variant_id"],
            "quantity": 50,
            "unit": "g",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["calories"] == 250
    assert body["variant_id"] == ids["packaged_variant_id"]
    assert body["quantity"] == 50
    assert body["unit"] == "g"
    assert body["name"] == "Britannia Good Day Cashew"


def test_add_entry_from_variant_by_pack(client):
    test_client, ids = client
    response = test_client.post(
        "/api/calories/entries",
        json={
            "date": "2026-10-20",
            "meal": "snack",
            "variant_id": ids["packaged_variant_id"],
            "unit": "pack",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["calories"] == 250
    assert body["quantity"] == 50


def test_add_entry_rejects_wrong_unit(client):
    test_client, ids = client
    response = test_client.post(
        "/api/calories/entries",
        json={
            "date": "2026-10-20",
            "meal": "snack",
            "variant_id": ids["packaged_variant_id"],
            "quantity": 100,
            "unit": "ml",
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unit_mismatch"


def test_add_manual_entry_still_works(client):
    test_client, _ = client
    response = test_client.post(
        "/api/calories/entries",
        json={
            "date": "2026-10-20",
            "meal": "lunch",
            "name": "Home dal",
            "calories": 180,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Home dal"
    assert body["calories"] == 180
    assert body["variant_id"] is None


def test_intake_targets_and_day_lock(client):
    test_client, ids = client
    day = "2026-10-27"

    added = test_client.post(
        "/api/calories/entries",
        json={
            "date": day,
            "meal": "snack",
            "variant_id": ids["packaged_variant_id"],
            "quantity": 50,
            "unit": "g",
        },
    )
    assert added.status_code == 201
    entry = added.json()
    assert entry["protein_g"] == 3.0
    assert entry["fat_g"] == 12.5

    day_log = test_client.get("/api/calories/day", params={"date": day})
    assert day_log.status_code == 200
    body = day_log.json()
    assert body["protein_consumed_g"] == 3.0
    assert body["fat_consumed_g"] == 12.5
    assert body["protein_goal_g"] == 60
    assert body["fat_goal_g"] == 56
    assert body["water_goal_ml"] == 2000

    done = test_client.put(
        "/api/calories/day/done", json={"date": day, "done": True}
    )
    assert done.status_code == 200
    assert done.json()["done"] is True

    locked_add = test_client.post(
        "/api/calories/entries",
        json={
            "date": day,
            "meal": "snack",
            "name": "Late snack",
            "calories": 100,
        },
    )
    assert locked_add.status_code == 409
    assert locked_add.json()["detail"]["code"] == "day_locked"

    locked_delete = test_client.delete(f"/api/calories/entries/{entry['id']}")
    assert locked_delete.status_code == 409

    reopened = test_client.put(
        "/api/calories/day/done", json={"date": day, "done": False}
    )
    assert reopened.status_code == 200
    assert reopened.json()["done"] is False


def test_water_target_uses_bmi():
    profile = Profile(
        name="Test",
        age=30,
        sex="male",
        height_cm=170,
        weight_kg=70,
        activity_level="moderate",
    )
    assert daily_nutrition_targets(profile, 2200).water_ml == 2450

    higher_bmi = Profile(
        name="Test",
        age=30,
        sex="male",
        height_cm=170,
        weight_kg=95,
        activity_level="moderate",
    )
    assert daily_nutrition_targets(higher_bmi, 2400).water_ml == 2850


def test_admin_endpoints_require_admin(client):
    test_client, _ = client
    response = test_client.get("/api/admin/foods")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "admin_required"


def test_admin_can_review_off_food(client):
    test_client, ids = client
    admin = User(
        id=ids["user_id"],
        username="food-admin",
        password_hash="x",
        role="admin",
    )
    regular = User(
        id=ids["user_id"],
        username="food-tester",
        password_hash="x",
        role="user",
    )

    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        listed = test_client.get(
            "/api/admin/foods",
            params={"source": "off", "is_verified": "false"},
        )
        assert listed.status_code == 200
        assert any(
            item["id"] == ids["off_food_id"]
            for item in listed.json()["items"]
        )

        updated = test_client.put(
            f"/api/admin/foods/{ids['off_food_id']}",
            headers={
                "X-Admin-Password": os.environ["ADMIN_CONFIRM_PASSWORD"]
            },
            json={
                "name": "Acme Review Bar Updated",
                "category": "packaged",
                "subcategory": "snack",
                "brand_name": "Acme",
                "description": "Nutrition reviewed manually.",
                "status": "approved",
                "is_verified": True,
                "review_note": "Checked the label against the pack image.",
                "variant": {
                    "kcal": 210,
                    "protein_g": 5.5,
                    "carbs_g": 30,
                    "fat_g": 8,
                    "base_amount": 100,
                    "base_unit": "g",
                },
            },
        )
        assert updated.status_code == 200
        body = updated.json()
        assert body["name"] == "Acme Review Bar Updated"
        assert body["brand"]["name"] == "Acme"
        assert body["is_verified"] is True
        assert body["default_variant"]["kcal"] == 210
        assert body["description"] == "Nutrition reviewed manually."

        history = test_client.get(
            f"/api/admin/foods/{ids['off_food_id']}/reviews"
        )
        assert history.status_code == 200
        reviews = history.json()["items"]
        assert reviews[0]["action"] == "approved"
        assert reviews[0]["is_verified"] is True
        assert reviews[0]["note"] == "Checked the label against the pack image."
        assert reviews[0]["reviewer_username"] == "food-tester"

        curated = test_client.get(
            "/api/admin/foods",
            params={"source": "curated", "is_verified": "false"},
        )
        assert curated.status_code == 200
        assert any(
            item["id"] == ids["packaged_id"]
            for item in curated.json()["items"]
        )

        reviewed = test_client.get(
            "/api/admin/foods",
            params={"source": "off", "is_verified": "false"},
        )
        assert reviewed.status_code == 200
        assert all(
            item["id"] != ids["off_food_id"]
            for item in reviewed.json()["items"]
        )

        verified = test_client.get(
            "/api/admin/foods",
            params={"source": "off", "is_verified": "true"},
        )
        assert verified.status_code == 200
        assert any(
            item["id"] == ids["off_food_id"]
            for item in verified.json()["items"]
        )
        app.dependency_overrides[get_current_user] = lambda: regular
        forbidden_history = test_client.get(
            f"/api/admin/foods/{ids['off_food_id']}/reviews"
        )
        assert forbidden_history.status_code == 403
    finally:
        app.dependency_overrides[get_current_user] = lambda: regular


def test_admin_pending_filter_excludes_approved_unverified(client):
    test_client, ids = client
    engine = create_engine(SYNC_DATABASE_URL)
    with Session(engine) as session:
        pending = Food(
            slug="pending-review-dal",
            name="Pending Review Dal",
            name_normalized="pending review dal",
            category="dal",
            base_unit="g",
            source="user",
            status="pending",
            is_verified=False,
            created_by_user_id=ids["user_id"],
        )
        session.add(pending)
        session.flush()
        session.add(
            FoodVariant(
                food_id=pending.id,
                state="cooked",
                label="",
                kcal=90,
                protein_g=5,
                carbs_g=10,
                fat_g=3,
                base_amount=100,
                base_unit="g",
                is_default=True,
            )
        )
        session.commit()
        pending_id = pending.id
    engine.dispose()

    admin = User(
        id=ids["user_id"],
        username="pending-admin",
        password_hash="x",
        role="admin",
    )
    regular = User(
        id=ids["user_id"],
        username="food-tester",
        password_hash="x",
        role="user",
    )

    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        response = test_client.get(
            "/api/admin/foods", params={"status": "pending"}
        )
        assert response.status_code == 200
        items = response.json()["items"]
        item_ids = {item["id"] for item in items}
        assert pending_id in item_ids
        assert ids["off_food_id"] not in item_ids
        assert all(item["status"] == "pending" for item in items)
    finally:
        app.dependency_overrides[get_current_user] = lambda: regular


def test_barcode_rate_limit(client, monkeypatch):
    test_client, _ = client
    reset_rate_limits()

    async def fake_lookup(barcode):
        return None

    monkeypatch.setattr("app.foods.lookup_off_product", fake_lookup)
    for index in range(12):
        response = test_client.post(
            "/api/foods/barcode/scan",
            json={"barcode": f"088888888{index:04d}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "queued"

    limited = test_client.post(
        "/api/foods/barcode/scan",
        json={"barcode": "0888888889999"},
    )
    assert limited.status_code == 429
    assert limited.json()["detail"]["code"] == "rate_limited"
    assert limited.headers["retry-after"]
    reset_rate_limits()
