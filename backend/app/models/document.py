import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base

class Document(Base):
    # Keep the core API document store separate from the legacy agent engine's
    # incompatible `documents` schema while sharing the same PostgreSQL database.
    __tablename__ = "app_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)  # pdf, docx, txt, png, etc.
    file_path = Column(String(512), nullable=False)
    masked_file_path = Column(String(512), nullable=True)
    status = Column(String(50), default="uploaded")  # uploaded, processing, completed, failed
    risk_score = Column(Integer, default=0)
    risk_level = Column(String(20), default="LOW")
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="documents")
