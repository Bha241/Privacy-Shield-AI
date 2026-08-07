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

DEFAULT_POSTGRES_URL = os.getenv("DATABASE_URL", POSTGRES_URL)


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
            logger.info(f"Successfully connected to PostgreSQL database at {target_pg_url}")
        except Exception as e:
            logger.error(f"PostgreSQL connection failed at {target_pg_url}: {e}")
            # Initialize engine for lazy/re-connection attempts without crashing module load
            self.engine = create_engine(target_pg_url, pool_pre_ping=True)

        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)


    def init_db(self):
        """Create all tables and seed initial RBAC & Compliance rule sets if not populated."""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info(f"Database schema initialized using {self.db_type}")
            self._seed_initial_data()
        except Exception as e:
            logger.warning(f"Database schema creation notice (Operating with fallback DB/In-memory): {e}")

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
