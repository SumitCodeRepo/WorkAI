"""
core/config.py
--------------
PURPOSE:
    Single source of truth for all application configuration.
    Values are read from the .env file at startup and exposed as a
    typed `settings` object used everywhere in the backend.

CONCEPT — Why Pydantic Settings?
    Hard-coding secrets (JWT keys, DB paths) in source code is a security risk
    and makes environment-specific deployments impossible.
    pydantic-settings reads variables from the OS environment or a .env file
    and validates their types automatically. If a required variable is missing
    or has the wrong type, the app crashes at startup with a clear error —
    much better than a silent misconfiguration discovered at runtime.

HOW TO USE:
    from core.config import settings
    print(settings.SECRET_KEY)   # always a str, guaranteed

ADDING A NEW SETTING:
    1. Add a typed field here with a sensible default.
    2. Add the variable name to backend/.env.
    3. Import `settings` where needed — no other changes required.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── JWT ──────────────────────────────────────────────────────────────────
    # Change SECRET_KEY to a long random string in production.
    # Anyone with this key can forge tokens — treat it like a password.
    SECRET_KEY: str = "change-this-to-a-long-random-secret-key-in-production"
    ALGORITHM: str = "HS256"                 # HMAC-SHA256 signing algorithm
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60    # tokens expire after 1 hour

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./chatbot.db"

    # ── Ollama (local LLM server) ─────────────────────────────────────────────
    # Ollama runs at localhost:11434 by default after `ollama serve`.
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    # Model used for chat/generation. Must be available via `ollama list`.
    OLLAMA_MODEL: str = "gpt-oss:120b-cloud"

    # ── Rate limiting ─────────────────────────────────────────────────────────
    # Applied to POST /chat/message via slowapi. Format: "<count>/<period>".
    # Period can be: second, minute, hour, day.
    RATE_LIMIT_CHAT: str = "20/minute"

    # Reads .env from the directory where uvicorn is launched (backend/).
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# Module-level singleton — import this object, never instantiate Settings again.
settings = Settings()
