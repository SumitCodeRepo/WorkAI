"""
auth/schemas.py
---------------
PURPOSE:
    Pydantic models (schemas) that define the shape of HTTP request bodies
    and response payloads for the authentication endpoints.

CONCEPT — Pydantic Validation:
    When FastAPI receives a POST request, it deserialises the JSON body into
    the Pydantic model declared in the route signature. If any field is missing
    or has the wrong type, FastAPI automatically returns a 422 Unprocessable
    Entity response with a detailed error — before your route code runs.

CONCEPT — Why separate schemas from ORM models?
    ORM models (db/models.py) describe database rows.
    Schemas describe what the API accepts and returns.
    Keeping them separate means you can safely expose only the fields you
    want (e.g. never return hashed_password) and evolve the API independently
    of the database schema.

SCHEMAS IN THIS FILE:
    RegisterRequest  — body for POST /auth/register
    LoginRequest     — body for POST /auth/login
    TokenResponse    — response from POST /auth/login
    UserResponse     — response from POST /auth/register and GET /auth/me
"""

from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator
from db.models import Department


class RegisterRequest(BaseModel):
    """
    Fields the client must send when creating a new account.

    email       — validated as a proper email address by Pydantic's EmailStr
    password    — plaintext; hashed server-side before storage (never logged)
    full_name   — optional display name
    department  — the user's home department; defaults to 'general'
    """
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    department: Department = Department.general

    @field_validator('email', mode='before')
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return v.strip().lower()


class LoginRequest(BaseModel):
    """Fields required to authenticate and receive a JWT."""
    email: EmailStr
    password: str

    @field_validator('email', mode='before')
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseModel):
    """
    Response returned after successful login.

    access_token — the JWT the client stores and sends in the
                   Authorization: Bearer <token> header on subsequent requests
    token_type   — always 'bearer' per OAuth2 convention
    """
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """
    Safe representation of a user returned by the API.
    hashed_password is intentionally excluded — it must never leave the server.

    model_config from_attributes=True allows this model to be built directly
    from a SQLAlchemy ORM User object (ORM → Pydantic conversion).
    """
    id: int
    email: str
    full_name: Optional[str]
    role: str
    department: str

    model_config = {"from_attributes": True}
