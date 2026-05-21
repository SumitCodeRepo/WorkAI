"""
auth/router.py
--------------
PURPOSE:
    Defines the three authentication HTTP endpoints:
      POST /auth/register  — create a new user account
      POST /auth/login     — verify credentials, return a JWT
      GET  /auth/me        — return the authenticated user's profile

CONCEPT — APIRouter:
    FastAPI's APIRouter is like a mini-app: you define routes on it, then
    mount it onto the main app with app.include_router(router).
    prefix="/auth" means every route here is automatically prefixed, so
    `@router.post("/register")` becomes `POST /auth/register`.

CONCEPT — Dependency Injection (Depends):
    FastAPI's `Depends(get_db)` automatically creates a DB session, passes it
    to the route function, and closes it when the request is done.
    This pattern means routes never manage session lifecycle directly.

CONCEPT — HTTP Status Codes:
    201 Created  — used for /register because a new resource was created
    200 OK       — default; used for /login and /me
    400 Bad Request — duplicate email
    401 Unauthorized — wrong password or invalid/expired token

SECURITY NOTE:
    /login returns the same generic error whether the email doesn't exist or
    the password is wrong. This prevents user enumeration — an attacker cannot
    tell which accounts exist by probing the login endpoint.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.logging_config import get_logger
from db.database import get_db
from db import models
from core.security import hash_password, verify_password, create_access_token, get_current_user
from .schemas import RegisterRequest, LoginRequest, TokenResponse, UserResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """
    Create a new user account.

    - Rejects duplicate emails with 400.
    - Hashes the password with bcrypt before storing.
    - Returns the created user (without the hashed password).
    """
    logger.info("Registration attempt for email: %s", body.email)

    existing = db.query(models.User).filter(models.User.email == body.email).first()
    if existing:
        logger.warning("Registration rejected — email already exists: %s", body.email)
        raise HTTPException(status_code=400, detail="Email already registered")

    user = models.User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        department=body.department,
        role=models.UserRole.user,   # all self-registered users start as 'user'
    )
    db.add(user)
    db.commit()
    db.refresh(user)   # reload from DB to get the auto-generated id and created_at

    logger.info("User registered successfully: id=%d email=%s", user.id, user.email)
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive a JWT access token",
)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate with email + password and return a signed JWT.

    The same 401 error is returned whether the email doesn't exist or the
    password is wrong. This prevents attackers from enumerating valid accounts.
    """
    logger.info("Login attempt for email: %s", body.email)

    user = db.query(models.User).filter(models.User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        # Deliberately vague: don't reveal whether email or password was wrong.
        logger.warning("Failed login attempt for email: %s", body.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    token = create_access_token({"sub": user.email})
    logger.info("Login successful: id=%d email=%s role=%s", user.id, user.email, user.role)
    return {"access_token": token, "token_type": "bearer"}


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the currently authenticated user's profile",
)
def me(current_user: models.User = Depends(get_current_user)):
    """
    Protected route — requires a valid JWT in the Authorization header.
    Returns the user profile for the owner of the token.

    FastAPI calls get_current_user() automatically via Depends() before this
    function runs. If the token is invalid or expired, a 401 is raised there
    and this function body never executes.
    """
    logger.debug("Profile fetched for user: %s", current_user.email)
    return current_user
