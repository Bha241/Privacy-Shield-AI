import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text
from app.core.database import Base

class AuditLogEntry(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type = Column(String(100), nullable=False)
    user_id = Column(String(36), nullable=True)
    document_id = Column(String(36), nullable=True)
    details = Column(Text, nullable=False)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
