"""
Central configuration, entirely environment-variable driven so operators can
tune behavior without touching code (thresholds, DB backend, API key, CORS).
"""
import os
from typing import List


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _get_list(name: str, default: str) -> List[str]:
    raw = os.environ.get(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


class Settings:
    # --- Auth ---
    # Structured as a simple shared-secret check today. To swap to JWT later,
    # replace the body of `auth.verify_api_key` with JWT decode/validate logic
    # and keep the same dependency signature so routes need no changes.
    API_KEY: str = os.environ.get("API_KEY", "changeme-dev-key")
    AUTH_MODE: str = os.environ.get("AUTH_MODE", "api_key")  # api_key | jwt (future)

    # --- Guardrail thresholds (0.0 - 1.0) ---
    THRESHOLD_FLAG: float = _get_float("THRESHOLD_FLAG", 0.5)
    THRESHOLD_BLOCK: float = _get_float("THRESHOLD_BLOCK", 0.85)

    # --- Database ---
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///./guardrail.db")

    # --- CORS ---
    CORS_ORIGINS: List[str] = _get_list("CORS_ORIGINS", "*")

    # --- Models ---
    # If "auto", the app tries the real ML models and transparently falls back
    # to lightweight heuristic stubs if the libraries/weights are unavailable.
    TEXT_MODEL_MODE: str = os.environ.get("TEXT_MODEL_MODE", "auto")  # auto|stub|ml
    IMAGE_MODEL_MODE: str = os.environ.get("IMAGE_MODEL_MODE", "auto")
    HF_IMAGE_MODEL: str = os.environ.get("HF_IMAGE_MODEL", "Falconsai/nsfw_image_detection")

    # --- Misc ---
    INPUT_PREVIEW_CHARS: int = int(os.environ.get("INPUT_PREVIEW_CHARS", "200"))
    APP_NAME: str = os.environ.get("APP_NAME", "Guardrail Moderation API")

    # --- JWT auth (human dashboard users: login, roles) ---
    # Separate from the x-api-key scheme used by /moderate/* (service-to-service).
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-change-me-in-prod")
    JWT_ALGORITHM: str = os.environ.get("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.environ.get("JWT_EXPIRE_MINUTES", "480"))

    # Bootstrap admin account, created automatically on first startup if no
    # users exist yet, so there's always a way to log in.
    ADMIN_USERNAME: str = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.environ.get("ADMIN_PASSWORD", "admin123")

    # --- Public social feed demo ---
    MEDIA_DIR: str = os.environ.get("MEDIA_DIR", "media")


settings = Settings()
