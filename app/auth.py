"""
Two independent auth schemes, on purpose:

1. x-api-key  -> used by /moderate/text and /moderate/image. This is the
   "service calling a service" path (your app's backend calling this API),
   so a shared secret is appropriate and simple.

2. JWT bearer token -> used by /auth/*, /audit/*, /analytics/*, /admin/*.
   This is the "human logs into a dashboard" path, so it carries an identity
   (username) and a role (admin / moderator / client) that routes can check.

Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib `hashlib`, no extra
native-compiled dependency needed) — never stored in plaintext.
"""
import base64
import hashlib
import hmac
import os
import time
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.config import settings

# ---------------------------------------------------------------------------
# x-api-key auth (service-to-service, for /moderate/*)
# ---------------------------------------------------------------------------
async def verify_api_key(x_api_key: str = Header(default=None, alias="x-api-key")) -> str:
    if not x_api_key or x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid x-api-key header",
        )
    return x_api_key


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_b64, digest_b64 = stored_hash.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT issuing / verification
# ---------------------------------------------------------------------------
def create_access_token(username: str, role: str) -> str:
    now = int(time.time())
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + settings.JWT_EXPIRE_MINUTES * 60,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


class CurrentUser:
    def __init__(self, username: str, role: str):
        self.username = username
        self.role = role


async def get_current_user(authorization: Optional[str] = Header(default=None)) -> CurrentUser:
    """Decodes a `Authorization: Bearer <token>` header into a CurrentUser."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header (expected 'Bearer <token>')",
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired, please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    return CurrentUser(username=payload["sub"], role=payload["role"])


def require_roles(*allowed_roles: str):
    """FastAPI dependency factory: require the caller's JWT role to be one of allowed_roles."""
    async def _checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(allowed_roles)}",
            )
        return user
    return _checker
