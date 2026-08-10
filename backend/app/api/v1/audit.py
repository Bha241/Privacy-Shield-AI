from fastapi import APIRouter
from app.agents.agents.audit_log_agent import AuditLogAgent

router = APIRouter(prefix="/audit", tags=["Audit & Compliance"])

@router.get("/logs")
async def get_audit_logs():
    return AuditLogAgent().get_all_logs()
