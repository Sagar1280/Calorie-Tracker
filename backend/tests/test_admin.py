import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import SYNC_DATABASE_URL, run_migrations
from app.limiter import reset_rate_limits
from app.main import app
from app.models import Food, FoodVariant, User

PASSWORD = os.environ["ADMIN_CONFIRM_PASSWORD"]
HEADERS = {"X-Admin-Password": PASSWORD}


@pytest.fixture(scope="module")
def client():
    reset_rate_limits()
    run_migrations()
    engine = create_engine(SYNC_DATABASE_URL)
    with Session(engine) as session:
        admin = User(
            username=f"admin-test-{uuid.uuid4().hex[:8]}",
            password_hash="x",
            role="admin",
        )
        session.add(admin)
        session.commit()
        admin_id = admin.id
    engine.dispose()

    current_user = User(
        id=admin_id,
        username="admin-test",
        password_hash="x",
        role="admin",
    )
    app.dependency_overrides[get_current_user] = lambda: current_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    reset_rate_limits()

    engine = create_engine(SYNC_DATABASE_URL)
    with Session(engine) as session:
        food_ids = list(
            session.execute(
                select(Food.id).where(Food.created_by_user_id == admin_id)
            ).scalars()
        )
        if food_ids:
            session.execute(
                delete(FoodVariant).where(FoodVariant.food_id.in_(food_ids))
            )
            session.execute(delete(Food).where(Food.id.in_(food_ids)))
        session.execute(delete(User).where(User.id == admin_id))
        session.commit()
    engine.dispose()


def _payload(name: str) -> dict:
    return {
        "name": name,
        "category": "dish",
        "subcategory": None,
        "brand_name": None,
        "description": "Created by an admin endpoint test.",
        "status": "pending",
        "is_verified": False,
        "review_note": "Test draft.",
        "variant": {
            "kcal": 120,
            "protein_g": 6,
            "carbs_g": 15,
            "fat_g": 4,
            "base_amount": 100,
            "base_unit": "g",
        },
    }


def _create(client: TestClient, name: str) -> dict:
    response = client.post(
        "/api/admin/foods", json=_payload(name), headers=HEADERS
    )
    assert response.status_code == 201
    return response.json()


def test_admin_mutations_require_confirmation_password(client):
    response = client.post(
        "/api/admin/foods", json=_payload("No Password Food")
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "admin_password_invalid"

    wrong = client.post(
        "/api/admin/foods",
        json=_payload("Wrong Password Food"),
        headers={"X-Admin-Password": "wrong"},
    )
    assert wrong.status_code == 403
    assert wrong.json()["detail"]["code"] == "admin_password_invalid"


def test_admin_can_create_update_and_bulk_review(client):
    suffix = uuid.uuid4().hex[:8]
    first = _create(client, f"Admin Test Dal {suffix}")
    second = _create(client, f"Admin Test Rice {suffix}")

    updated = client.put(
        f"/api/admin/foods/{first['id']}",
        headers=HEADERS,
        json={
            **_payload(first["name"]),
            "status": "approved",
            "is_verified": True,
            "review_note": "Approved individually.",
            "variant": {
                "kcal": 140,
                "protein_g": 7,
                "carbs_g": 18,
                "fat_g": 5,
                "base_amount": 100,
                "base_unit": "g",
            },
        },
    )
    assert updated.status_code == 200
    assert updated.json()["is_verified"] is True
    assert updated.json()["default_variant"]["kcal"] == 140

    ids = [first["id"], second["id"]]
    approved = client.post(
        "/api/admin/foods/bulk",
        headers=HEADERS,
        json={
            "ids": ids,
            "action": "approve",
            "review_note": "Approved as a batch.",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["affected"] == 2

    for food_id in ids:
        food = client.get(f"/api/foods/{food_id}")
        assert food.status_code == 200
        assert food.json()["status"] == "approved"
        assert food.json()["is_verified"] is True

    history = client.get(f"/api/admin/foods/{second['id']}/reviews")
    assert history.status_code == 200
    assert history.json()["items"][0]["action"] == "approved"
    assert history.json()["items"][0]["note"] == "Approved as a batch."

    rejected = client.post(
        "/api/admin/foods/bulk",
        headers=HEADERS,
        json={"ids": [second["id"]], "action": "reject"},
    )
    assert rejected.status_code == 200
    rejected_food = client.get(f"/api/foods/{second['id']}").json()
    assert rejected_food["status"] == "rejected"
    assert rejected_food["is_verified"] is False

    deleted = client.post(
        "/api/admin/foods/bulk",
        headers=HEADERS,
        json={"ids": ids, "action": "delete"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["affected"] == 2
    for food_id in ids:
        assert client.get(f"/api/foods/{food_id}").status_code == 404
