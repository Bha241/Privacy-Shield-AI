import os
from pathlib import Path
from typing import List, Union, Optional
from pydantic import AnyHttpUrl, validator
from pydantic_settings import BaseSettings

ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

class Settings(BaseSettings):
    PROJECT_NAME: str = "PrivacyShieldAI Enterprise SaaS"
    VERSION: str = "4.0.0"
    API_V1_STR: str = "/api/v1"
    
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-enterprise-key-privacyshield-ai-2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./privacyshield.db")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    APP_TIMEZONE: str = os.getenv("APP_TIMEZONE", "Asia/Kolkata")

    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000"
    ]

    # Redaction settings
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "gAAAAABl8d90877597048babfac740793522f83_default_key=")

    # Database & External Services
    POSTGRES_USER: Optional[str] = "postgres"
    POSTGRES_PASSWORD: Optional[str] = "Bhanu@1729"
    POSTGRES_HOST: Optional[str] = "localhost"
    POSTGRES_PORT: Optional[int] = 5432
    POSTGRES_DB: Optional[str] = "privacyshield"

    GROQ_API_KEY: Optional[str] = None
    GGUF_MODEL_PATH: Optional[str] = None

    LANGSMITH_TRACING: Optional[str] = "false"
    LANGSMITH_API_KEY: Optional[str] = None
    LANGSMITH_PROJECT: Optional[str] = "PrivacyShieldAI"
    LANGSMITH_ENDPOINT: Optional[str] = "https://api.smith.langchain.com"
    LANGSMITH_HIDE_INPUTS: Optional[str] = "true"
    LANGSMITH_HIDE_OUTPUTS: Optional[str] = "true"
    LANGSMITH_HIDE_METADATA: Optional[str] = "false"

    class Config:
        case_sensitive = True
        env_file = str(ROOT_ENV_FILE)
        extra = "ignore"

settings = Settings()
