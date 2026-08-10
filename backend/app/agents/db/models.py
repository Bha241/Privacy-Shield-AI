from datetime import datetime
import json
import uuid
from typing import Optional, List, Dict, Any
from enum import Enum

from sqlalchemy import (
    Column, String, Float, Integer, Text, Boolean, DateTime, Date, ForeignKey, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import declarative_base, relationship
from pydantic import BaseModel, Field

Base = declarative_base()


class UserRoleEnum(str, Enum):
    GENERAL = "General"
    COMPLIANCE = "Compliance"
    ADMIN = "Admin"
    AUDITOR = "Auditor"


class DocumentStatusEnum(str, Enum):
    PENDING = "PENDING"
    SANITIZED = "SANITIZED"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"


class MaskingMethodEnum(str, Enum):
    REDACTION = "REDACTION"
    TOKENIZATION = "TOKENIZATION"
    GENERALIZATION = "GENERALIZATION"
    HASH_MASK = "HASH_MASK"


# ==========================================
# 1. Document Entity (PostgreSQL)
# ==========================================
class DocumentModel(Base):
    """
    Core Document metadata store.
    Attributes: document_id, filename, category, risk_score, status, upload_timestamp, owner_id
    """
    __tablename__ = "documents"

    document_id = Column(String(64), primary_key=True, default=lambda: f"doc_{uuid.uuid4().hex[:12]}")
    filename = Column(String(255), nullable=False)
    category = Column(String(64), nullable=False, default="General")
    risk_score = Column(Float, nullable=False, default=0.0)
    status = Column(String(32), nullable=False, default=DocumentStatusEnum.PENDING.value)
    upload_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    owner_id = Column(String(64), ForeignKey("users_roles.user_id"), nullable=True, default="usr_admin")
    organization_id = Column(String(64), nullable=False, default="org_default")
    original_text = Column(Text, nullable=True)
    masked_text = Column(Text, nullable=True)
    token_mapping_json = Column(Text, nullable=True)
    detected_entities_json = Column(Text, nullable=True)

    # Relationships
    pii_entities = relationship("PIIEntityModel", back_populates="document", cascade="all, delete-orphan")
    pii_mappings = relationship("PIIMappingModel", back_populates="document", cascade="all, delete-orphan")
    sanitized_chunks = relationship("SanitizedChunkModel", back_populates="document", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLogEntryModel", back_populates="document", cascade="all, delete-orphan")
    owner = relationship("UserRoleModel", back_populates="documents")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "category": self.category,
            "risk_score": self.risk_score,
            "status": self.status,
            "upload_timestamp": self.upload_timestamp.isoformat() if self.upload_timestamp else None,
            "owner_id": self.owner_id,
            "organization_id": self.organization_id,
            "original_text": self.original_text,
            "masked_text": self.masked_text,
            "token_mapping_json": self.token_mapping_json,
            "detected_entities_json": self.detected_entities_json
        }


# ==========================================
# 2. PII Entity (PostgreSQL Metadata + Encrypted Store)
# ==========================================
class PIIEntityModel(Base):
    """
    Detected PII metadata entity.
    Attributes: entity_id, document_id, type, offset_start, offset_end, confidence, masking_method
    """
    __tablename__ = "pii_entities"

    entity_id = Column(String(64), primary_key=True, default=lambda: f"ent_{uuid.uuid4().hex[:12]}")
    document_id = Column(String(64), ForeignKey("documents.document_id"), nullable=False)
    type = Column(String(64), nullable=False)  # NAME, PHONE, AADHAAR, PAN, EMAIL, etc.
    offset_start = Column(Integer, nullable=False)
    offset_end = Column(Integer, nullable=False)
    confidence = Column(Float, nullable=False, default=0.90)
    masking_method = Column(String(64), nullable=False, default=MaskingMethodEnum.TOKENIZATION.value)

    document = relationship("DocumentModel", back_populates="pii_entities")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "document_id": self.document_id,
            "type": self.type,
            "offset_start": self.offset_start,
            "offset_end": self.offset_end,
            "confidence": self.confidence,
            "masking_method": self.masking_method
        }


class PIIMappingModel(Base):
    """Document-scoped reversible token mapping metadata."""
    __tablename__ = "pii_mappings"
    __table_args__ = (UniqueConstraint("document_id", "token", name="uq_pii_mapping_document_token"),)

    mapping_id = Column(String(64), primary_key=True, default=lambda: f"map_{uuid.uuid4().hex[:12]}")
    document_id = Column(String(64), ForeignKey("documents.document_id"), nullable=False)
    token = Column(String(128), nullable=False)
    entity_type = Column(String(64), nullable=False)
    original_value = Column(Text, nullable=False)
    occurrence_index = Column(Integer, nullable=False, default=1)
    start_offset = Column(Integer, nullable=True)
    end_offset = Column(Integer, nullable=True)
    approved = Column(Boolean, nullable=False, default=True)

    document = relationship("DocumentModel", back_populates="pii_mappings")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mapping_id": self.mapping_id,
            "document_id": self.document_id,
            "token": self.token,
            "entity_type": self.entity_type,
            "original_value": self.original_value,
            "occurrence_index": self.occurrence_index,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "approved": self.approved,
        }


# ==========================================
# 3. Sanitized Chunk Entity (Vector DB Store)
# ==========================================
class SanitizedChunkModel(Base):
    """
    Sanitized Chunk metadata and vector embedding reference.
    Attributes: chunk_id, document_id, text, embedding_vector, page_ref
    """
    __tablename__ = "sanitized_chunks"

    chunk_id = Column(String(64), primary_key=True, default=lambda: f"chk_{uuid.uuid4().hex[:12]}")
    document_id = Column(String(64), ForeignKey("documents.document_id"), nullable=False)
    text = Column(Text, nullable=False)
    embedding_vector = Column(Text, nullable=True)  # JSON-encoded float array / vector
    page_ref = Column(String(32), nullable=True, default="1")
    chunk_index = Column(Integer, nullable=False, default=1)

    document = relationship("DocumentModel", back_populates="sanitized_chunks")

    def set_vector(self, vector_list: List[float]):
        self.embedding_vector = json.dumps(vector_list)

    def get_vector(self) -> List[float]:
        return json.loads(self.embedding_vector) if self.embedding_vector else []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "text": self.text,
            "embedding_vector_dim": len(self.get_vector()),
            "page_ref": self.page_ref,
            "chunk_index": self.chunk_index
        }


# ==========================================
# 4. Audit Log Entry (PostgreSQL Hash-Chained)
# ==========================================
class AuditLogEntryModel(Base):
    """
    Hash-chained immutable compliance log entry as per DPDP Act 2025.
    Attributes: log_id, actor_id, action_type, document_id, timestamp, prev_hash, entry_hash
    """
    __tablename__ = "audit_log_entries"

    log_id = Column(String(64), primary_key=True, default=lambda: f"log_{uuid.uuid4().hex[:12]}")
    actor_id = Column(String(64), nullable=False, default="usr_system")
    action_type = Column(String(64), nullable=False)
    document_id = Column(String(64), ForeignKey("documents.document_id"), nullable=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    prev_hash = Column(String(64), nullable=False, default="0" * 64)
    entry_hash = Column(String(64), nullable=False)
    details_json = Column(Text, nullable=True)

    document = relationship("DocumentModel", back_populates="audit_logs")

    def to_dict(self) -> Dict[str, Any]:
        try:
            details = json.loads(self.details_json) if self.details_json else {}
        except (TypeError, ValueError):
            details = {"raw_details": self.details_json or ""}
        return {
            "log_id": self.log_id,
            "event_id": self.log_id,
            "id": self.log_id,
            "actor_id": self.actor_id,
            "user_id": self.actor_id,
            "action_type": self.action_type,
            "event_type": self.action_type,
            "document_id": self.document_id,
            "document_name": self.document.filename if self.document else details.get("document_name"),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
            "origin_ip": details.get("origin_ip"),
            "details": details,
            "metadata": details,
        }


# ==========================================
# 5. User / Role Entity (PostgreSQL)
# ==========================================
class UserRoleModel(Base):
    """
    User & Role RBAC entity.
    Attributes: user_id, name, role (General/Compliance/Admin/Auditor), permissions
    """
    __tablename__ = "users_roles"

    user_id = Column(String(64), primary_key=True, default=lambda: f"usr_{uuid.uuid4().hex[:12]}")
    name = Column(String(128), nullable=False)
    role = Column(String(32), nullable=False, default=UserRoleEnum.GENERAL.value)
    permissions_json = Column(Text, nullable=False, default="[]")

    documents = relationship("DocumentModel", back_populates="owner")

    def set_permissions(self, perms: List[str]):
        self.permissions_json = json.dumps(perms)

    def get_permissions(self) -> List[str]:
        return json.loads(self.permissions_json) if self.permissions_json else []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "role": self.role,
            "permissions": self.get_permissions()
        }


# ==========================================
# 6. Compliance Rule Set (PostgreSQL)
# ==========================================
class ComplianceRuleSetModel(Base):
    """
    Regulatory compliance policy rule set.
    Attributes: ruleset_id, jurisdiction, category, masking_policy, version, active_flag
    """
    __tablename__ = "compliance_rule_sets"

    ruleset_id = Column(String(64), primary_key=True, default=lambda: f"rule_{uuid.uuid4().hex[:12]}")
    jurisdiction = Column(String(64), nullable=False, default="IN_DPDP_2025")
    category = Column(String(64), nullable=False, default="General")
    masking_policy_json = Column(Text, nullable=False, default="{}")
    version = Column(String(32), nullable=False, default="v1.0.0")
    active_flag = Column(Boolean, nullable=False, default=True)

    def set_masking_policy(self, policy: Dict[str, Any]):
        self.masking_policy_json = json.dumps(policy)

    def get_masking_policy(self) -> Dict[str, Any]:
        return json.loads(self.masking_policy_json) if self.masking_policy_json else {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ruleset_id": self.ruleset_id,
            "jurisdiction": self.jurisdiction,
            "category": self.category,
            "masking_policy": self.get_masking_policy(),
            "version": self.version,
            "active_flag": self.active_flag
        }


class RetentionPolicyModel(Base):
    """Workspace-scoped calendar-date retention policy and daily-run state."""
    __tablename__ = "retention_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_retention_policy_organization"),
        CheckConstraint("retention_days >= 7 AND retention_days <= 21", name="ck_retention_days_range"),
    )

    policy_id = Column(String(64), primary_key=True, default=lambda: f"ret_{uuid.uuid4().hex[:12]}")
    organization_id = Column(String(64), nullable=False, default="org_default")
    retention_days = Column(Integer, nullable=False, default=7)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_cleanup_date = Column(Date, nullable=True)
    last_cleanup_at = Column(DateTime, nullable=True)


# ==========================================
# Pydantic Schemas for API Layer
# ==========================================
class DocumentSchema(BaseModel):
    document_id: str
    filename: str
    category: str
    risk_score: float
    status: DocumentStatusEnum
    upload_timestamp: datetime
    owner_id: Optional[str] = "usr_admin"

    class Config:
        from_attributes = True


class PIIEntitySchema(BaseModel):
    entity_id: str
    document_id: str
    type: str
    offset_start: int
    offset_end: int
    confidence: float
    masking_method: MaskingMethodEnum

    class Config:
        from_attributes = True


class SanitizedChunkSchema(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    embedding_vector: Optional[List[float]] = []
    page_ref: Optional[str] = "1"

    class Config:
        from_attributes = True


class AuditLogEntrySchema(BaseModel):
    log_id: str
    actor_id: str
    action_type: str
    document_id: Optional[str] = None
    timestamp: datetime
    prev_hash: str
    entry_hash: str
    details: Optional[Dict[str, Any]] = {}

    class Config:
        from_attributes = True


class UserRoleSchema(BaseModel):
    user_id: str
    name: str
    role: UserRoleEnum
    permissions: List[str]

    class Config:
        from_attributes = True


class ComplianceRuleSetSchema(BaseModel):
    ruleset_id: str
    jurisdiction: str
    category: str
    masking_policy: Dict[str, Any]
    version: str
    active_flag: bool

    class Config:
        from_attributes = True
