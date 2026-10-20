from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from ..auth import (
    DUMMY_PASSWORD_HASH,
    SESSION_COOKIE,
    clear_session_cookie,
    get_current_user,
    hash_password,
    hash_token,
    issue_session,
    set_session_cookie,
    verify_password,
)
from ..config import ALLOW_REGISTRATION
from ..db import SessionLocal
from ..limiter import enforce_rate_limit
from ..models import AuthSession, User, utc_now
from ..schemas import LoginIn, RegisterIn, UserOut
from ..serializers import to_user_out

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/register", response_model=UserOut, status_code=201)
async def register(
    payload: RegisterIn, request: Request, response: Response
) -> UserOut:
    if not ALLOW_REGISTRATION:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "registration_disabled",
                "message": "New accounts are disabled on this server.",
            },
        )

    enforce_rate_limit(
        "register",
        _client_key(request),
        limit=5,
        window_seconds=600,
        message="Too many account attempts. Please wait and try again.",
    )
    password_hash = await run_in_threadpool(hash_password, payload.password)

    async with SessionLocal() as session:
        user = User(username=payload.username, password_hash=password_hash)
        session.add(user)
        try:
            await session.flush()
            token = issue_session(session, user.id)
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "username_taken",
                    "message": "That username is already taken.",
                },
            ) from exc
        result = to_user_out(user)

    set_session_cookie(response, token)
    return result


@router.post("/login", response_model=UserOut)
async def login(
    payload: LoginIn, request: Request, response: Response
) -> UserOut:
    client = _client_key(request)
    enforce_rate_limit(
        "login-ip",
        client,
        limit=30,
        window_seconds=300,
        message="Too many sign-in attempts. Please wait and try again.",
    )
    enforce_rate_limit(
        "login-user",
        f"{client}:{payload.username}",
        limit=10,
        window_seconds=300,
        message="Too many sign-in attempts. Please wait and try again.",
    )

    async with SessionLocal() as session:
        user = (
            await session.execute(
                select(User).where(User.username == payload.username)
            )
        ).scalar_one_or_none()

        stored_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
        password_ok = await run_in_threadpool(
            verify_password, payload.password, stored_hash
        )

        if user is None or not password_ok:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "invalid_credentials",
                    "message": "Invalid username or password.",
                },
            )

        now = utc_now()
        await session.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
        token = issue_session(session, user.id)
        await session.commit()
        result = to_user_out(user)

    set_session_cookie(response, token)
    return result


@router.post("/logout", status_code=204)
async def logout(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    if session_token:
        async with SessionLocal() as session:
            await session.execute(
                delete(AuthSession).where(
                    AuthSession.token_hash == hash_token(session_token)
                )
            )
            await session.commit()

    response = Response(status_code=204)
    clear_session_cookie(response)
    return response


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return to_user_out(user)
