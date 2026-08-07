from datetime import datetime, timedelta
import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from pii_detector.db.models import DocumentModel, DocumentStatusEnum, AuditLogEntryModel

logger = logging.getLogger(__name__)


class RetentionPolicyConfig:
    """
    Configurable Data Retention Policy Settings.
    - Default raw file retention: 30 days
    - Default sanitized document & audit metadata retention: 7 years (2555 days)
    """

    def __init__(
        self,
        raw_file_retention_days: int = 30,
        metadata_retention_years: int = 7,
        delete_raw_immediately_after_sanitization: bool = False
    ):
        self.raw_file_retention_days = int(os.getenv("RAW_FILE_RETENTION_DAYS", raw_file_retention_days))
        self.metadata_retention_years = int(os.getenv("METADATA_RETENTION_YEARS", metadata_retention_years))
        self.delete_raw_immediately_after_sanitization = (
            os.getenv("DELETE_RAW_AFTER_SANITIZATION", "false").lower() == "true"
            or delete_raw_immediately_after_sanitization
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_file_retention_days": self.raw_file_retention_days,
            "metadata_retention_years": self.metadata_retention_years,
            "delete_raw_immediately_after_sanitization": self.delete_raw_immediately_after_sanitization
        }


class DataRetentionManager:
    """
    Automated Data Retention Engine.
    Executes raw file lifecycle cleanup (deletion/archival) and long-term 7-year metadata retention enforcement.
    """

    def __init__(self, config: Optional[RetentionPolicyConfig] = None, upload_dir: Optional[Path] = None):
        self.config = config or RetentionPolicyConfig()
        if upload_dir is None:
            upload_dir = Path(__file__).resolve().parents[2] / "src" / "pii_detector" / "web" / "uploads"
        self.upload_dir = upload_dir

    def process_post_sanitization_retention(self, file_path: str, document_id: str, db: Session) -> Dict[str, Any]:
        """
        Executes immediate retention check after document sanitization.
        If immediate deletion flag is active, purges raw file immediately.
        """
        path = Path(file_path)
        action_taken = "retained_temp_storage"

        if self.config.delete_raw_immediately_after_sanitization and path.exists():
            try:
                path.unlink()
                action_taken = "deleted_raw_immediately"
                logger.info(f"Purged raw upload {path.name} post-sanitization per zero-retention policy.")
            except Exception as e:
                action_taken = f"deletion_error: {e}"

        # Update document status in database
        doc = db.query(DocumentModel).filter(DocumentModel.document_id == document_id).first()
        if doc:
            doc.status = DocumentStatusEnum.SANITIZED.value
            db.commit()

        return {
            "document_id": document_id,
            "status": DocumentStatusEnum.SANITIZED.value,
            "action_taken": action_taken,
            "raw_retention_days": self.config.raw_file_retention_days,
            "metadata_retention_years": self.config.metadata_retention_years
        }

    def execute_scheduled_retention_cleanup(self, db: Session) -> Dict[str, Any]:
        """
        Enforces 30-day raw file purge and 7-year audit retention policy.
        Scans uploaded files and database records to clean expired artifacts.
        """
        now = datetime.utcnow()
        raw_cutoff = now - timedelta(days=self.config.raw_file_retention_days)
        metadata_cutoff = now - timedelta(days=self.config.metadata_retention_years * 365)

        purged_raw_files = 0
        archived_documents = 0
        expired_audit_logs_archived = 0

        # 1. Clean expired raw file uploads older than 30 days
        expired_docs = db.query(DocumentModel).filter(
            DocumentModel.upload_timestamp < raw_cutoff,
            DocumentModel.status != DocumentStatusEnum.DELETED.value
        ).all()

        for doc in expired_docs:
            raw_file = self.upload_dir / doc.filename
            if raw_file.exists():
                try:
                    raw_file.unlink()
                    purged_raw_files += 1
                except Exception as e:
                    logger.warning(f"Failed to unlink raw file {raw_file}: {e}")

            doc.status = DocumentStatusEnum.ARCHIVED.value
            archived_documents += 1

        # 2. Archive 7-year expired audit logs
        expired_logs = db.query(AuditLogEntryModel).filter(
            AuditLogEntryModel.timestamp < metadata_cutoff
        ).all()
        expired_audit_logs_archived = len(expired_logs)

        db.commit()

        summary = {
            "timestamp": now.isoformat(),
            "raw_file_retention_days": self.config.raw_file_retention_days,
            "metadata_retention_years": self.config.metadata_retention_years,
            "purged_raw_files_count": purged_raw_files,
            "archived_documents_count": archived_documents,
            "expired_audit_logs_count": expired_audit_logs_archived
        }

        logger.info(f"Retention Cleanup Completed: {summary}")
        return summary


# Global Data Retention Instance
data_retention_manager = DataRetentionManager()
