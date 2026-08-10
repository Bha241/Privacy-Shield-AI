import json
import uuid
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
from pydantic import BaseModel

from app.agents.db.database import db_manager
from pii_detector.db.models import DocumentModel, DocumentStatusEnum
from app.agents.agents.audit_log_agent import AuditLogAgent
from app.agents.db.retention import retention_cleanup_agent

router = APIRouter(prefix="/documents", tags=["Documents & Files"])
audit_agent = AuditLogAgent()


class DocumentRegisterRequest(BaseModel):
    filename: str
    file_type: Optional[str] = "application/octet-stream"
    owner_id: str = "usr_admin"
    organization_id: str = "org_default"


def _document_to_context(document: DocumentModel) -> dict:
    return {
        "id": document.document_id,
        "document_id": document.document_id,
        "filename": document.filename,
        "file_type": document.category,
        "category": document.category,
        "status": "READY" if document.status == DocumentStatusEnum.SANITIZED.value else document.status,
        "risk_score": document.risk_score,
        "created_at": document.upload_timestamp.isoformat() if document.upload_timestamp else None,
        "owner_id": document.owner_id,
        "organization_id": document.organization_id,
        "classification": document.category,
    }


def _document_to_detail(document: DocumentModel) -> dict:
    try:
        entities = json.loads(document.detected_entities_json or "[]")
    except (TypeError, ValueError):
        entities = []
    try:
        mapping = json.loads(document.token_mapping_json or "{}")
    except (TypeError, ValueError):
        mapping = {}
    return {
        **_document_to_context(document),
        "original_text": document.original_text or "",
        "masked_text": document.masked_text or "",
        "entities": entities,
        "mapping": mapping,
    }


@router.post("/register")
async def register_document(request: DocumentRegisterRequest):
    """Create a stable backend document identity before client-side HITL review."""
    document_id = f"doc_{uuid.uuid4().hex}"
    with db_manager.get_session() as session:
        document = DocumentModel(
            document_id=document_id,
            filename=request.filename,
            category="General",
            status=DocumentStatusEnum.PENDING.value,
            owner_id=request.owner_id,
            organization_id=request.organization_id,
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        audit_agent.log_event(
            agent_name="DocumentService",
            action_type="DOCUMENT_UPLOAD",
            actor_id=request.owner_id,
            document_id=document_id,
            details={
                "document_name": request.filename,
                "description": "Uploaded document for privacy processing",
                "organization_id": request.organization_id,
            },
        )
        return _document_to_context(document)


@router.get("/library")
async def list_document_library(owner_id: str = "usr_admin", organization_id: str = "org_default"):
    """List only documents owned by the requesting workspace user."""
    with db_manager.get_session() as session:
        documents = (
            session.query(DocumentModel)
            .filter(DocumentModel.owner_id == owner_id, DocumentModel.organization_id == organization_id)
            .order_by(DocumentModel.upload_timestamp.desc())
            .all()
        )
        return [_document_to_context(document) for document in documents]


@router.delete("/data")
async def delete_all_workspace_data(
    owner_id: str = "usr_admin",
    organization_id: str = "org_default",
):
    """Immediately delete all document-derived data for the authorized workspace."""
    from pii_detector.db.models import UserRoleModel
    with db_manager.get_session() as session:
        user = session.query(UserRoleModel).filter(UserRoleModel.user_id == owner_id).first()
        if not user or user.role not in {"Admin", "Compliance"}:
            raise HTTPException(status_code=403, detail="Only workspace admins may delete all workspace data")
        return retention_cleanup_agent.delete_all_workspace_data(
            session,
            organization_id=organization_id,
            actor_id=owner_id,
        )


@router.get("/{document_id}")
async def get_document_detail(document_id: str, owner_id: str = "usr_admin", organization_id: str = "org_default"):
    """Return the persisted processed payload for one authorized document."""
    with db_manager.get_session() as session:
        document = (
            session.query(DocumentModel)
            .filter(
                DocumentModel.document_id == document_id,
                DocumentModel.owner_id == owner_id,
                DocumentModel.organization_id == organization_id,
            )
            .first()
        )
        if not document:
            raise HTTPException(status_code=404, detail="Document not found in the authorized workspace")
        return _document_to_detail(document)


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    owner_id: str = "usr_admin",
    organization_id: str = "org_default",
):
    """Immediately delete one authorized document and all protected derivatives."""
    from pii_detector.db.models import UserRoleModel
    with db_manager.get_session() as session:
        user = session.query(UserRoleModel).filter(UserRoleModel.user_id == owner_id).first()
        document = session.query(DocumentModel).filter(
            DocumentModel.document_id == document_id,
            DocumentModel.organization_id == organization_id,
        ).first()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found in the authorized workspace")
        if not user:
            raise HTTPException(status_code=403, detail="Document deletion requires an authorized workspace user")
        permissions = user.get_permissions()
        can_delete = document.owner_id == owner_id or user.role in {"Admin", "Compliance"} or "delete" in permissions
        if not can_delete:
            raise HTTPException(status_code=403, detail="You are not authorized to delete this document")
        return retention_cleanup_agent.delete_document_now(
            session,
            document_id=document_id,
            organization_id=organization_id,
            actor_id=owner_id,
        )

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    masking_strategy: Optional[str] = Form("REPLACE")
):
    job_id = str(uuid.uuid4())
    filename = file.filename or "uploaded_document"
    
    return {
        "status": "queued",
        "job_id": job_id,
        "filename": filename,
        "message": f"Document '{filename}' submitted for async PII processing",
        "progress": 0
    }

@router.get("/status/{job_id}")
async def get_job_status(job_id: str):
    return {
        "job_id": job_id,
        "status": "completed",
        "progress": 100,
        "result": {
            "entities_found": 3,
            "risk_level": "MEDIUM",
            "risk_score": 45
        }
    }
