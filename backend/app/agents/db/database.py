import os
import logging
import json
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from pii_detector.db.models import (
    Base, UserRoleModel, ComplianceRuleSetModel, UserRoleEnum
)

logger = logging.getLogger(__name__)

# Default Database Paths & Connection Strings
BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "src" / "pii_detector" / "web" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

from pii_detector.config import POSTGRES_URL

# The core API uses asyncpg, while this legacy agent subsystem uses sync SQLAlchemy.
# Always use the normalized synchronous URL here so both subsystems share the same database.
DEFAULT_POSTGRES_URL = POSTGRES_URL
SQLITE_FALLBACK_URL = f"sqlite:///{(Path(__file__).resolve().parents[3] / 'privacyshield.db').as_posix()}"


class DatabaseManager:
    """
    Database Manager for PostgreSQL.
    Manages session lifecycle, table initialization, and regulatory seeds.
    """

    def __init__(self, postgres_url: str = DEFAULT_POSTGRES_URL):
        self.engine = None
        self.db_type = "PostgreSQL"
        self.SessionLocal = None

        target_pg_url = postgres_url or DEFAULT_POSTGRES_URL
        try:
            self.engine = create_engine(target_pg_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Successfully connected to the primary PostgreSQL database")
        except Exception as e:
            logger.error(f"PostgreSQL connection failed; using SQLite fallback: {e}")
            self.engine = create_engine(SQLITE_FALLBACK_URL, pool_pre_ping=True)
            self.db_type = "SQLite fallback"

        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)


    def init_db(self):
        """Create all tables and seed initial RBAC & Compliance rule sets if not populated."""
        try:
            Base.metadata.create_all(bind=self.engine)
            self._ensure_document_columns()
            self._ensure_retention_columns()
            logger.info(f"Database schema initialized using {self.db_type}")
            self._seed_initial_data()
            logger.info("Database seed data initialized")
        except Exception as e:
            if self.db_type == "PostgreSQL":
                logger.warning(f"PostgreSQL schema initialization failed; using SQLite fallback: {e}")
                self.engine.dispose()
                self.engine = create_engine(SQLITE_FALLBACK_URL, pool_pre_ping=True)
                self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
                self.db_type = "SQLite fallback"
                Base.metadata.create_all(bind=self.engine)
                self._ensure_document_columns()
                self._ensure_retention_columns()
                self._seed_initial_data()
            else:
                logger.warning(f"Database schema creation failed: {e}")

    def _ensure_document_columns(self):
        """Add shared processed-document fields for existing installations."""
        with self.engine.begin() as conn:
            if self.db_type == "PostgreSQL":
                conn.execute(text(
                    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS organization_id VARCHAR(64) NOT NULL DEFAULT 'org_default'"
                ))
                conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS original_text TEXT"))
                conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS masked_text TEXT"))
                conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS token_mapping_json TEXT"))
                conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS detected_entities_json TEXT"))
                conn.execute(text("ALTER TABLE sanitized_chunks ADD COLUMN IF NOT EXISTS chunk_index INTEGER NOT NULL DEFAULT 1"))
            else:
                columns = conn.execute(text("PRAGMA table_info(documents)")).fetchall()
                if not any(row[1] == "organization_id" for row in columns):
                    conn.execute(text(
                        "ALTER TABLE documents ADD COLUMN organization_id VARCHAR(64) NOT NULL DEFAULT 'org_default'"
                    ))
                existing = {row[1] for row in columns}
                for name in ("original_text", "masked_text", "token_mapping_json", "detected_entities_json"):
                    if name not in existing:
                        conn.execute(text(f"ALTER TABLE documents ADD COLUMN {name} TEXT"))
                chunk_columns = conn.execute(text("PRAGMA table_info(sanitized_chunks)")).fetchall()
                if not any(row[1] == "chunk_index" for row in chunk_columns):
                    conn.execute(text("ALTER TABLE sanitized_chunks ADD COLUMN chunk_index INTEGER NOT NULL DEFAULT 1"))

    def _ensure_retention_columns(self):
        """Add retention run-state columns without recreating existing tables."""
        with self.engine.begin() as conn:
            if self.db_type == "PostgreSQL":
                conn.execute(text("ALTER TABLE retention_policies ADD COLUMN IF NOT EXISTS last_cleanup_date DATE"))
                conn.execute(text("ALTER TABLE retention_policies ADD COLUMN IF NOT EXISTS last_cleanup_at TIMESTAMP"))
            else:
                columns = conn.execute(text("PRAGMA table_info(retention_policies)" )).fetchall()
                existing = {row[1] for row in columns}
                if "last_cleanup_date" not in existing:
                    conn.execute(text("ALTER TABLE retention_policies ADD COLUMN last_cleanup_date DATE"))
                if "last_cleanup_at" not in existing:
                    conn.execute(text("ALTER TABLE retention_policies ADD COLUMN last_cleanup_at DATETIME"))

    def get_session(self) -> Session:

        return self.SessionLocal()

    def _seed_initial_data(self):
        session = self.SessionLocal()
        try:
            # Seed default User Roles if empty
            if session.query(UserRoleModel).count() == 0:
                admin_user = UserRoleModel(
                    user_id="usr_admin",
                    name="System Administrator",
                    role=UserRoleEnum.ADMIN.value,
                    permissions_json=json.dumps(["read", "write", "hitl_verify", "demask", "admin_override", "audit_view"])
                )
                compliance_officer = UserRoleModel(
                    user_id="usr_compliance",
                    name="DPDP Compliance Officer",
                    role=UserRoleEnum.COMPLIANCE.value,
                    permissions_json=json.dumps(["read", "hitl_verify", "rule_manage", "audit_view", "retention_clean"])
                )
                auditor_user = UserRoleModel(
                    user_id="usr_auditor",
                    name="External Security Auditor",
                    role=UserRoleEnum.AUDITOR.value,
                    permissions_json=json.dumps(["read", "audit_view", "integrity_check"])
                )
                general_user = UserRoleModel(
                    user_id="usr_general",
                    name="Standard User",
                    role=UserRoleEnum.GENERAL.value,
                    permissions_json=json.dumps(["read", "upload", "qna"])
                )
                session.add_all([admin_user, compliance_officer, auditor_user, general_user])
                logger.info("Seeded default User & Role RBAC entries.")

            # Seed default Compliance Rule Sets if empty
            if session.query(ComplianceRuleSetModel).count() == 0:
                dpdp_rule = ComplianceRuleSetModel(
                    ruleset_id="rule_dpdp_2025",
                    jurisdiction="IN_DPDP_2025",
                    category="General",
                    masking_policy_json=json.dumps({
                        "NAME": "TOKENIZATION",
                        "PHONE": "TOKENIZATION",
                        "EMAIL": "TOKENIZATION",
                        "AADHAAR": "REDACTION",
                        "PAN": "REDACTION",
                        "MEDICAL_RECORD_NUMBER": "HASH_MASK",
                        "CREDIT_CARD": "REDACTION"
                    }),
                    version="v1.0.0",
                    active_flag=True
                )
                gdpr_rule = ComplianceRuleSetModel(
                    ruleset_id="rule_gdpr_eu",
                    jurisdiction="EU_GDPR",
                    category="Medical",
                    masking_policy_json=json.dumps({
                        "NAME": "GENERALIZATION",
                        "LOCATION": "GENERALIZATION",
                        "DIAGNOSIS": "TOKENIZATION",
                        "NATIONAL_ID": "REDACTION"
                    }),
                    version="v1.0.0",
                    active_flag=True
                )
                session.add_all([dpdp_rule, gdpr_rule])
                logger.info("Seeded default DPDP Act 2025 & GDPR Compliance Rule Sets.")

            session.commit()
        except Exception as e:
            session.rollback()
            logger.warning(f"Database initial seed warning: {e}")
        finally:
            session.close()


# Global Singleton Database Instance
db_manager = DatabaseManager()


def get_db() -> Generator[Session, None, None]:
    """Dependency helper for route handlers to obtain a database session."""
    db = db_manager.get_session()
    try:
        yield db
    finally:
        db.close()
