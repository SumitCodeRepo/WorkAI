"""
core/security.py
----------------
PURPOSE:
    All authentication and authorisation logic lives here.
    This keeps security code in one auditable place rather than scattered
    across routers.

CONCEPT — Password Hashing (bcrypt):
    bcrypt is a slow hashing algorithm designed specifically for passwords.
    Slowness is intentional — it makes brute-force attacks impractical.
    It automatically generates a unique random salt for each password so two
    users with the same password produce completely different hashes.

    Flow:  register → hash_password(plain) → store hash
           login    → verify_password(plain, stored_hash) → True/False

CONCEPT — JWT (JSON Web Tokens):
    A JWT has three base64-encoded parts separated by dots:
        header.payload.signature
    The payload contains claims like { "sub": "user@email.com", "exp": 1234567890 }.
    The signature is an HMAC-SHA256 hash of header+payload using SECRET_KEY.
    The server never stores the token — it verifies the signature on every request.

    Flow:  login  → create_access_token({"sub": email}) → return token to client
           request → get_current_user() → decode token → look up user in DB

CONCEPT — FastAPI Depends():
    `get_current_user` and `require_admin` are FastAPI dependencies.
    Declare them as default parameters of a route function and FastAPI
    automatically calls them before the route body runs, injecting the result.

EXPORTS:
    hash_password(password)       → hashed string
    verify_password(plain, hash)  → bool
    create_access_token(data)     → JWT string
    get_current_user(token, db)   → User (FastAPI dependency)
    require_admin(current_user)   → User, raises 403 if not admin (FastAPI dependency)
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from core.logging_config import get_logger
from .config import settings
from db.database import get_db
from db import models

logger = get_logger(__name__)

# CryptContext manages which hashing scheme is active and handles migrations
# if we ever switch algorithms. "deprecated='auto'" auto-marks old hashes for rehash.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2PasswordBearer tells FastAPI to expect an "Authorization: Bearer <token>"
# header and extract the token value from it automatically.
# tokenUrl is used only for the /docs UI — it points to the login endpoint.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Return a bcrypt hash of `password`. Store this; never store the plain text."""
    hashed = pwd_context.hash(password)
    logger.debug("Password hashed successfully")
    return hashed


def verify_password(plain: str, hashed: str) -> bool:
    """
    Return True if `plain` matches the stored `hashed` password.
    Uses constant-time comparison internally to prevent timing attacks.
    """
    result = pwd_context.verify(plain, hashed)
    logger.debug("Password verification result: %s", result)
    return result


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    """
    Create a signed JWT containing `data` as claims, plus an expiry claim.

    Args:
        data: Dict of claims to embed, e.g. {"sub": "user@example.com"}.
              "sub" (subject) is the standard JWT claim for the user identifier.

    Returns:
        Signed JWT string to return to the client.
    """
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload["exp"] = expire

    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    logger.info("Access token created for subject: %s", data.get("sub"))
    return token


# ── FastAPI dependencies ──────────────────────────────────────────────────────

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    """
    FastAPI dependency — decodes and validates the JWT, then fetches the user.

    Called automatically by FastAPI for any route that declares:
        current_user: models.User = Depends(get_current_user)

    Raises:
        401 Unauthorized — if the token is missing, expired, or tampered with.
        401 Unauthorized — if the email in the token no longer exists in the DB.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            logger.warning("JWT decoded but 'sub' claim is missing")
            raise credentials_exception
    except JWTError as exc:
        logger.warning("JWT decode failed: %s", exc)
        raise credentials_exception

    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        logger.warning("Valid JWT but user not found in DB: %s", email)
        raise credentials_exception

    logger.debug("Authenticated user: %s (role=%s)", user.email, user.role)
    return user


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    """
    FastAPI dependency — extends get_current_user with an admin role check.

    Use on routes that only admins should reach (document upload, user management).

    Raises:
        403 Forbidden — if the authenticated user's role is not 'admin'.
    """
    if current_user.role != models.UserRole.admin:
        logger.warning(
            "Admin route accessed by non-admin user: %s (role=%s)",
            current_user.email, current_user.role,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    logger.debug("Admin access granted to: %s", current_user.email)
    return current_user
