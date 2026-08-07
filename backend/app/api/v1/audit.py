from fastapi import APIRouter
from datetime import datetime

router = APIRouter(prefix="/audit", tags=["Audit & Compliance"])

@router.get("/logs")
async def get_audit_logs():
    return [
        {
            "id": "audit-1",
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "PII_REDACTION",
            "user_id": "user-demo-123",
            "details": "Redacted 3 PII entities (Aadhaar, Email, Phone)",
            "ip_address": "127.0.0.1"
        },
        {
            "id": "audit-2",
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "DOCUMENT_UPLOAD",
            "user_id": "user-demo-123",
            "details": "Uploaded confidential_contract.pdf for OCR processing",
            "ip_address": "127.0.0.1"
        }
    ]
