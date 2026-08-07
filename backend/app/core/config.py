import os
from typing import List, Union, Optional
from pydantic import AnyHttpUrl, validator
from pydantic_settings import BaseSettings

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

    LANGCHAIN_TRACING_V2: Optional[str] = "false"
    LANGCHAIN_API_KEY: Optional[str] = None
    LANGCHAIN_PROJECT: Optional[str] = None
    LANGCHAIN_ENDPOINT: Optional[str] = None

    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"

settings = Settings()
