"""Centralized, calendar-date based data retention service.

The service deliberately operates on the existing synchronous application DB
used by the RAG/vector subsystem. It never drops schemas or schedules work per
document. All expiration decisions are made here from one configured timezone.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, text, update
from sqlalchemy.orm import Session

from app.core.config import settings
from pii_detector.db.models import (
    AuditLogEntryModel,
    DocumentModel,
    DocumentStatusEnum,
    PIIMappingModel,
    PIIEntityModel,
    RetentionPolicyModel,
    SanitizedChunkModel,
)

logger = logging.getLogger(__name__)

MIN_RETENTION_DAYS = 7
MAX_RETENTION_DAYS = 21
RETENTION_LOCK_KEY = "privacyshield:daily-retention-cleanup"


def retention_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(settings.APP_TIMEZONE)
    except Exception:
        logger.warning("Invalid APP_TIMEZONE=%r; using UTC", settings.APP_TIMEZONE)
        return ZoneInfo("UTC")


def local_date_for_timestamp(value: Optional[datetime], tz: Optional[ZoneInfo] = None) -> Optional[date]:
    """Convert a stored UTC timestamp to the configured workspace calendar date."""
    if value is None:
        return None
    zone = tz or retention_timezone()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(zone).date()


def cutoff_date_for(retention_days: int, today: Optional[date] = None) -> date:
    validate_retention_days(retention_days)
    return (today or datetime.now(retention_timezone()).date()) - timedelta(days=retention_days)


def validate_retention_days(value: int) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"retention_days must be an integer between {MIN_RETENTION_DAYS} and {MAX_RETENTION_DAYS}") from exc
    if not MIN_RETENTION_DAYS <= days <= MAX_RETENTION_DAYS:
        raise ValueError(f"retention_days must be between {MIN_RETENTION_DAYS} and {MAX_RETENTION_DAYS} days")
    return days


def next_cleanup_at(now: Optional[datetime] = None) -> datetime:
    """Return the next local midnight as an aware datetime."""
    zone = retention_timezone()
    current = now.astimezone(zone) if now else datetime.now(zone)
    tomorrow = current.date() + timedelta(days=1)
    return datetime.combine(tomorrow, time.min, tzinfo=zone)


class RetentionCleanupAgent:
    """Owns policy lookup, expiry calculation, transactional purge and audit."""

    def __init__(self, upload_dir: Optional[Path] = None, output_dir: Optional[Path] = None):
        base = Path(__file__).resolve().parents[1]
        self.upload_dir = upload_dir or (base / "web" / "uploads")
        self.output_dir = output_dir or (base / "web" / "output")
        self.extra_upload_dir = Path(__file__).resolve().parents[3] / "temp_uploads"

    def get_or_create_policy(self, db: Session, organization_id: str = "org_default") -> RetentionPolicyModel:
        policy = (
            db.query(RetentionPolicyModel)
            .filter(RetentionPolicyModel.organization_id == organization_id)
            .first()
        )
        if policy:
            validate_retention_days(policy.retention_days)
            return policy
        policy = RetentionPolicyModel(organization_id=organization_id, retention_days=MIN_RETENTION_DAYS)
        db.add(policy)
        db.flush()
        return policy

    def _acquire_lock(self, db: Session) -> bool:
        """Use a PostgreSQL transaction advisory lock; SQLite is single-process here."""
        bind = db.get_bind()
        if bind.dialect.name != "postgresql":
            return True
        result = db.execute(text("SELECT pg_try_advisory_xact_lock(hashtext(:lock_key))"), {"lock_key": RETENTION_LOCK_KEY})
        return bool(result.scalar())

    def _safe_file_paths(self, filename: str) -> Iterable[Path]:
        if not filename:
            return []
        candidate_name = Path(filename).name
        stem = Path(candidate_name).stem
        paths = [
            self.upload_dir / candidate_name,
            self.extra_upload_dir / candidate_name,
            self.output_dir / f"{stem}_masked.txt",
            self.output_dir / f"{stem}_mapping.json",
        ]
        safe_paths = []
        for path in paths:
            try:
                resolved_root = path.parent.resolve()
                resolved_path = path.resolve()
                if resolved_path.parent == resolved_root:
                    safe_paths.append(resolved_path)
            except OSError:
                continue
        return safe_paths

    def _delete_stored_files(self, documents: Iterable[DocumentModel]) -> int:
        deleted = 0
        for document in documents:
            for path in self._safe_file_paths(document.filename):
                if path.exists() and path.is_file():
                    try:
                        path.unlink()
                        deleted += 1
                    except OSError as exc:
                        logger.warning("Could not remove expired file %s: %s", path, exc)
        return deleted

    def _invalidate_runtime_state(self, document_ids: set[str]) -> None:
        if not document_ids:
            return
        try:
            from app.agents.document_cache import document_cache
            document_cache.remove_many(document_ids)
        except Exception as exc:
            logger.warning("Document cache invalidation failed: %s", exc)
        try:
            from app.agents.db.vector_store import vector_store_manager
            vector_store_manager.remove_documents(document_ids)
        except Exception as exc:
            logger.warning("Vector cache invalidation failed: %s", exc)
        try:
            from app.api.v1.pii import rag_agent
            if rag_agent:
                for doc_id in document_ids:
                    rag_agent.doc_texts.pop(doc_id, None)
                    rag_agent.doc_mappings.pop(doc_id, None)
                    rag_agent.doc_classifications.pop(doc_id, None)
                    rag_agent.file_names_by_doc_id.pop(doc_id, None)
                    rag_agent.file_name_to_doc_id.pop(doc_id, None)
                    if rag_agent.current_document_id == doc_id:
                        rag_agent.current_document_id = None
        except Exception as exc:
            logger.warning("RAG runtime state invalidation failed: %s", exc)

    def purge_expired(
        self,
        db: Session,
        organization_id: str = "org_default",
        now: Optional[datetime] = None,
        actor_id: str = "usr_system",
        mark_daily_run: bool = False,
    ) -> Dict[str, Any]:
        if not self._acquire_lock(db):
            db.rollback()
            return {"status": "skipped_locked", "documents_deleted": 0, "vector_chunks_deleted": 0, "pii_mappings_deleted": 0}

        policy = self.get_or_create_policy(db, organization_id)
        today = (now.astimezone(retention_timezone()).date() if now and now.tzinfo else (now.date() if now else datetime.now(retention_timezone()).date()))
        cutoff = cutoff_date_for(policy.retention_days, today)
        documents = (
            db.query(DocumentModel)
            .filter(DocumentModel.organization_id == organization_id, DocumentModel.status != DocumentStatusEnum.DELETED.value)
            .all()
        )
        expired = [doc for doc in documents if (local_date_for_timestamp(doc.upload_timestamp) or today) <= cutoff]
        expired_ids = {doc.document_id for doc in expired}

        summary: Dict[str, Any] = {
            "status": "completed",
            "retention_days": policy.retention_days,
            "cutoff_date": cutoff.isoformat(),
            "timezone": settings.APP_TIMEZONE,
            "documents_deleted": 0,
            "vector_chunks_deleted": 0,
            "pii_mappings_deleted": 0,
            "pii_entities_deleted": 0,
            "stored_files_deleted": 0,
        }
        if expired_ids:
            summary["vector_chunks_deleted"] = db.query(SanitizedChunkModel).filter(SanitizedChunkModel.document_id.in_(expired_ids)).delete(synchronize_session=False)
            summary["pii_mappings_deleted"] = db.query(PIIMappingModel).filter(PIIMappingModel.document_id.in_(expired_ids)).delete(synchronize_session=False)
            summary["pii_entities_deleted"] = db.query(PIIEntityModel).filter(PIIEntityModel.document_id.in_(expired_ids)).delete(synchronize_session=False)
            # Preserve audit rows as safe metadata while releasing the FK to the deleted document.
            db.query(AuditLogEntryModel).filter(AuditLogEntryModel.document_id.in_(expired_ids)).update({AuditLogEntryModel.document_id: None}, synchronize_session=False)
            summary["stored_files_deleted"] = self._delete_stored_files(expired)
            db.query(DocumentModel).filter(DocumentModel.document_id.in_(expired_ids)).delete(synchronize_session=False)
            summary["documents_deleted"] = len(expired_ids)
            self._invalidate_runtime_state(expired_ids)

        if mark_daily_run:
            policy.last_cleanup_date = today
            policy.last_cleanup_at = datetime.utcnow()
        db.commit()

        from app.agents.agents.audit_log_agent import AuditLogAgent
        AuditLogAgent().log_event(
            agent_name="RetentionCleanupAgent",
            action_type="RETENTION_PURGE",
            actor_id=actor_id,
            details={
                "organization_id": organization_id,
                "retention_days": policy.retention_days,
                "cutoff_date": cutoff.isoformat(),
                "documents_deleted": summary["documents_deleted"],
                "vector_chunks_deleted": summary["vector_chunks_deleted"],
                "pii_mappings_deleted": summary["pii_mappings_deleted"],
                "pii_entities_deleted": summary["pii_entities_deleted"],
                "stored_files_deleted": summary["stored_files_deleted"],
            },
        )
        return summary

    def run_daily(self, db: Session, organization_id: str = "org_default") -> Dict[str, Any]:
        policy = self.get_or_create_policy(db, organization_id)
        today = datetime.now(retention_timezone()).date()
        if policy.last_cleanup_date == today:
            db.commit()
            return {"status": "already_completed", "retention_days": policy.retention_days, "documents_deleted": 0}
        return self.purge_expired(db, organization_id=organization_id, mark_daily_run=True)

    def delete_document_now(
        self,
        db: Session,
        document_id: str,
        organization_id: str = "org_default",
        actor_id: str = "usr_system",
    ) -> Dict[str, Any]:
        """Immediately delete one authorized document, independent of retention age."""
        document = (
            db.query(DocumentModel)
            .filter(DocumentModel.document_id == document_id, DocumentModel.organization_id == organization_id)
            .first()
        )
        if not document:
            return {"status": "not_found", "document_id": document_id, "documents_deleted": 0}

        document_name = document.filename
        vector_count = db.query(SanitizedChunkModel).filter(SanitizedChunkModel.document_id == document_id).delete(synchronize_session=False)
        mapping_count = db.query(PIIMappingModel).filter(PIIMappingModel.document_id == document_id).delete(synchronize_session=False)
        entity_count = db.query(PIIEntityModel).filter(PIIEntityModel.document_id == document_id).delete(synchronize_session=False)
        # Keep the audit trail as safe metadata, but remove the FK to the deleted row.
        db.query(AuditLogEntryModel).filter(AuditLogEntryModel.document_id == document_id).update({AuditLogEntryModel.document_id: None}, synchronize_session=False)
        file_count = self._delete_stored_files([document])
        db.query(DocumentModel).filter(DocumentModel.document_id == document_id).delete(synchronize_session=False)
        self._invalidate_runtime_state({document_id})
        db.commit()

        from app.agents.agents.audit_log_agent import AuditLogAgent
        AuditLogAgent().log_event(
            agent_name="DocumentService",
            action_type="DOCUMENT_DELETED",
            actor_id=actor_id,
            # The document row is gone; preserve the safe ID in details_json
            # without violating the audit table's nullable FK.
            document_id=None,
            persist_document_fk=False,
            details={
                "document_id": document_id,
                "document_name": document_name,
                "organization_id": organization_id,
                "deletion_reason": "manual_user_delete",
                "vector_chunks_deleted": vector_count,
                "pii_mappings_deleted": mapping_count,
                "pii_entities_deleted": entity_count,
                "stored_files_deleted": file_count,
            },
        )
        return {
            "status": "deleted",
            "document_id": document_id,
            "document_name": document_name,
            "documents_deleted": 1,
            "vector_chunks_deleted": vector_count,
            "pii_mappings_deleted": mapping_count,
            "pii_entities_deleted": entity_count,
            "stored_files_deleted": file_count,
        }

    def delete_all_workspace_data(
        self,
        db: Session,
        organization_id: str = "org_default",
        actor_id: str = "usr_system",
    ) -> Dict[str, Any]:
        """Immediately delete all document-derived data for one workspace."""
        documents = db.query(DocumentModel).filter(DocumentModel.organization_id == organization_id).all()
        document_ids = {document.document_id for document in documents}
        vector_count = db.query(SanitizedChunkModel).filter(SanitizedChunkModel.document_id.in_(document_ids)).delete(synchronize_session=False) if document_ids else 0
        mapping_count = db.query(PIIMappingModel).filter(PIIMappingModel.document_id.in_(document_ids)).delete(synchronize_session=False) if document_ids else 0
        entity_count = db.query(PIIEntityModel).filter(PIIEntityModel.document_id.in_(document_ids)).delete(synchronize_session=False) if document_ids else 0
        db.query(AuditLogEntryModel).filter(AuditLogEntryModel.document_id.in_(document_ids)).update({AuditLogEntryModel.document_id: None}, synchronize_session=False) if document_ids else None
        file_count = self._delete_stored_files(documents)
        if document_ids:
            db.query(DocumentModel).filter(DocumentModel.document_id.in_(document_ids)).delete(synchronize_session=False)
            self._invalidate_runtime_state(document_ids)
        db.commit()

        from app.agents.agents.audit_log_agent import AuditLogAgent
        AuditLogAgent().log_event(
            agent_name="DocumentService",
            action_type="DATA_PURGE_ALL",
            actor_id=actor_id,
            document_id=None,
            persist_document_fk=False,
            details={
                "organization_id": organization_id,
                "documents_deleted": len(document_ids),
                "vector_chunks_deleted": vector_count,
                "pii_mappings_deleted": mapping_count,
                "pii_entities_deleted": entity_count,
                "stored_files_deleted": file_count,
                "reason": "manual_all_data_delete",
            },
        )
        return {
            "status": "deleted",
            "organization_id": organization_id,
            "documents_deleted": len(document_ids),
            "vector_chunks_deleted": vector_count,
            "pii_mappings_deleted": mapping_count,
            "pii_entities_deleted": entity_count,
            "stored_files_deleted": file_count,
        }


class DataRetentionManager:
    """Compatibility facade for the legacy agent-engine routes."""

    def __init__(self, **kwargs: Any):
        self.agent = RetentionCleanupAgent(**kwargs)
        self.config = self

    def to_dict(self) -> Dict[str, Any]:
        return {"retention_days": MIN_RETENTION_DAYS, "timezone": settings.APP_TIMEZONE}

    def process_post_sanitization_retention(self, file_path: str, document_id: str, db: Session) -> Dict[str, Any]:
        document = db.query(DocumentModel).filter(DocumentModel.document_id == document_id).first()
        if document:
            document.status = DocumentStatusEnum.SANITIZED.value
        return {"document_id": document_id, "status": DocumentStatusEnum.SANITIZED.value, "action_taken": "retained_until_policy_expiry", "retention_days": MIN_RETENTION_DAYS}

    def execute_scheduled_retention_cleanup(self, db: Session) -> Dict[str, Any]:
        return self.agent.run_daily(db)


retention_cleanup_agent = RetentionCleanupAgent()
data_retention_manager = DataRetentionManager()


def run_daily_retention_cleanup() -> Dict[str, Any]:
    from pii_detector.db.database import db_manager
    db = db_manager.get_session()
    try:
        return retention_cleanup_agent.run_daily(db)
    finally:
        db.close()


async def retention_scheduler_loop() -> None:
    """One backend-owned daily scheduler; browser state is never involved."""
    while True:
        now = datetime.now(retention_timezone())
        next_run = next_cleanup_at(now)
        await asyncio.sleep(max(1, (next_run - now).total_seconds()))
        try:
            await asyncio.to_thread(run_daily_retention_cleanup)
        except Exception:
            logger.exception("Daily retention cleanup failed")
