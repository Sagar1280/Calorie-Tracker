import base64
import hashlib
import hmac
import os
import secrets
from datetime import timedelta
from typing import Annotated

from fastapi import Cookie, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import SessionLocal
from .models import AuthSession, User, utc_now

SESSION_COOKIE = "ct_session"
SESSION_TTL = timedelta(days=30)
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "").strip().lower() in {
    "1",
    "true",
    "yes",
}

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64
_SCRYPT_MAXMEM = 64 * 1024 * 1024


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
        maxmem=_SCRYPT_MAXMEM,
    )
    return "$".join(
        [
            "scrypt",
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = encoded.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(hash_b64.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
            maxmem=_SCRYPT_MAXMEM,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


DUMMY_PASSWORD_HASH = hash_password("calorie-tracker-dummy-password")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={
            "code": "not_authenticated",
            "message": "Please sign in to continue.",
        },
    )


async def get_current_user(
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User:
    if not session_token:
        raise unauthorized()

    now = utc_now()
    async with SessionLocal() as session:
        result = await session.execute(
            select(User)
            .join(AuthSession, AuthSession.user_id == User.id)
            .where(
                AuthSession.token_hash == hash_token(session_token),
                AuthSession.expires_at > now,
            )
        )
        user = result.scalar_one_or_none()

    if user is None:
        raise unauthorized()
    return user


def issue_session(session: AsyncSession, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    session.add(
        AuthSession(
            token_hash=hash_token(token),
            user_id=user_id,
            created_at=utc_now(),
            expires_at=utc_now() + SESSION_TTL,
        )
    )
    return token


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )
