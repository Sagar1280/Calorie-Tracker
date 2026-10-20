import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from app.db import SYNC_DATABASE_URL, run_migrations
from app.limiter import reset_rate_limits
from app.main import app
from app.models import AuthSession, CalorieEntry, DayLog, Profile, User


def _delete_user(user_id: int) -> None:
    engine = create_engine(SYNC_DATABASE_URL)
    with Session(engine) as session:
        session.execute(delete(CalorieEntry).where(CalorieEntry.user_id == user_id))
        session.execute(delete(DayLog).where(DayLog.user_id == user_id))
        session.execute(delete(Profile).where(Profile.user_id == user_id))
        session.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
        session.execute(delete(User).where(User.id == user_id))
        session.commit()
    engine.dispose()


@pytest.fixture(scope="module")
def client():
    reset_rate_limits()
    run_migrations()
    with TestClient(app) as test_client:
        yield test_client
    reset_rate_limits()


def _register(client: TestClient) -> tuple[int, str, str]:
    username = f"auth-test-{uuid.uuid4().hex[:10]}"
    password = "Auth-Test-9f3a!"
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
    )
    assert response.status_code == 201
    return response.json()["id"], username, password


def test_health_and_security_headers(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "same-origin"
    assert "camera=(self)" in response.headers["Permissions-Policy"]


def test_register_login_logout_flow(client):
    user_id, username, password = _register(client)
    try:
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["username"] == username

        assert client.post("/api/auth/logout").status_code == 204
        assert client.get("/api/auth/me").status_code == 401

        login = client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        assert login.status_code == 200
        assert login.json()["username"] == username
        assert login.cookies.get("ct_session") or client.cookies.get("ct_session")
    finally:
        _delete_user(user_id)


def test_registration_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.ALLOW_REGISTRATION", False)
    response = client.post(
        "/api/auth/register",
        json={"username": f"closed-{uuid.uuid4().hex[:8]}", "password": "Closed-9f3a!"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "registration_disabled"


def test_login_is_rate_limited(client):
    user_id, username, _ = _register(client)
    try:
        for _ in range(10):
            response = client.post(
                "/api/auth/login",
                json={"username": username, "password": "wrong-password"},
            )
            assert response.status_code == 401

        blocked = client.post(
            "/api/auth/login",
            json={"username": username, "password": "wrong-password"},
        )
        assert blocked.status_code == 429
        assert blocked.json()["detail"]["code"] == "rate_limited"
        assert int(blocked.headers["Retry-After"]) > 0
    finally:
        reset_rate_limits()
        _delete_user(user_id)
