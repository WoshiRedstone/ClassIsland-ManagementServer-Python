"""Authentication helpers.

Mirrors the behaviour of ASP.NET Core Identity used by the original server:

* password hashing uses the ``PasswordHasher<TUser>`` V3 format
  (PBKDF2 / HMAC-SHA512, 100000 iterations, 128 bit salt, 256 bit subkey),
  which keeps existing password hashes interchangeable;
* the bearer token response carries ``tokenType`` / ``accessToken`` /
  ``expiresIn`` / ``refreshToken`` exactly like ``AddBearerToken()`` does.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import os
import secrets
import struct
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status

from .db import User

# ---------------------------------------------------------------------------
# password hashing (Identity V3 format)
# ---------------------------------------------------------------------------

_ITERATION_COUNT = 100_000
_SALT_SIZE = 128 // 8
_SUBKEY_SIZE = 256 // 8
_FORMAT_V3 = 0x01
_PRF_HMACSHA512 = 0x02


def hash_password(password: str) -> str:
    """``PasswordHasher.HashPassword`` compatible output (base64 text)."""
    salt = os.urandom(_SALT_SIZE)
    subkey = hashlib.pbkdf2_hmac(
        "sha512", password.encode("utf-8"), salt, _ITERATION_COUNT, _SUBKEY_SIZE
    )
    payload = (
        bytes([_FORMAT_V3, _PRF_HMACSHA512])
        + struct.pack(">I", _ITERATION_COUNT)
        + struct.pack(">I", _SALT_SIZE)
        + salt
        + subkey
    )
    return base64.b64encode(payload).decode("ascii")


def verify_password(hashed: str | None, password: str) -> bool:
    if not hashed:
        return False
    try:
        payload = base64.b64decode(hashed)
    except Exception:
        return False
    if len(payload) < 13:
        return False
    fmt = payload[0]
    if fmt != _FORMAT_V3:
        return False
    iterations = struct.unpack(">I", payload[2:6])[0]
    salt_len = struct.unpack(">I", payload[6:10])[0]
    if salt_len <= 0 or len(payload) < 10 + salt_len:
        return False
    salt = payload[10:10 + salt_len]
    subkey = payload[10 + salt_len:]
    computed = hashlib.pbkdf2_hmac("sha512", password.encode("utf-8"), salt, iterations, len(subkey))
    return hmac.compare_digest(computed, subkey)


# ---------------------------------------------------------------------------
# tokens
# ---------------------------------------------------------------------------

ACCESS_TOKEN_LIFETIME = 3600  # seconds, Identity BearerToken default
REFRESH_TOKEN_LIFETIME = 14 * 24 * 3600  # seconds
_ALGORITHM = "HS256"
_SECRET_CACHE: dict[str, str] = {}


def _secret(database: Any) -> str:
    """Server secret persisted in ``organization_settings`` so tokens survive
    restarts."""
    key = "CyreneMspJwtSecret"
    cached = _SECRET_CACHE.get(key)
    if cached:
        return cached
    value = database.get_setting(key)
    if not value:
        value = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode("ascii")
        database.set_setting(key, "CyreneMsp", value)
    _SECRET_CACHE[key] = value
    return value


def create_access_token(database: Any, user: User, lifetime: int = ACCESS_TOKEN_LIFETIME) -> str:
    issued = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": user.Id,
        "name": user.UserName,
        "roles": user.role_names,
        "stamp": user.SecurityStamp,
        "iat": int(issued.timestamp()),
        "nbf": int(issued.timestamp()),
        "exp": int((issued + dt.timedelta(seconds=lifetime)).timestamp()),
        "typ": "access",
        "iss": "ClassIsland.ManagementServer",
    }
    return jwt.encode(payload, _secret(database), algorithm=_ALGORITHM)


def create_refresh_token(database: Any, user: User) -> str:
    issued = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": user.Id,
        "stamp": user.SecurityStamp,
        "iat": int(issued.timestamp()),
        "exp": int((issued + dt.timedelta(seconds=REFRESH_TOKEN_LIFETIME)).timestamp()),
        "typ": "refresh",
        "iss": "ClassIsland.ManagementServer",
    }
    return jwt.encode(payload, _secret(database), algorithm=_ALGORITHM)


def decode_token(database: Any, token: str, expected_type: str = "access") -> dict[str, Any] | None:
    try:
        payload = jwt.decode(
            token,
            _secret(database),
            algorithms=[_ALGORITHM],
            issuer="ClassIsland.ManagementServer",
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != expected_type:
        return None
    return payload


def token_response(database: Any, user: User) -> dict[str, Any]:
    return {
        "tokenType": "Bearer",
        "accessToken": create_access_token(database, user),
        "expiresIn": ACCESS_TOKEN_LIFETIME,
        "refreshToken": create_refresh_token(database, user),
    }


# ---------------------------------------------------------------------------
# request dependencies
# ---------------------------------------------------------------------------


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not header:
        return None
    parts = header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def current_user(request: Request) -> User:
    """Resolve the caller from the ``Authorization: Bearer`` header."""
    database = request.app.state.database
    token = _bearer_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    payload = decode_token(database, token, "access")
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    with database.open() as db:
        user = db.get(User, payload.get("sub"))
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
        if payload.get("stamp") and user.SecurityStamp and payload["stamp"] != user.SecurityStamp:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
        _ = user.role_names
        db.expunge(user)
    return user


def require_roles(*roles: str):
    """``[Authorize(Roles = "...")]`` equivalent."""

    def dependency(user: User = Depends(current_user)) -> User:
        if roles:
            names = set(user.role_names)
            if "Admin" not in names and not names.intersection(roles):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return user

    return dependency
