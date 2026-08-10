from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agents.db.database import db_manager
from app.agents.db.retention import (
    MAX_RETENTION_DAYS,
    MIN_RETENTION_DAYS,
    cutoff_date_for,
    local_date_for_timestamp,
    next_cleanup_at,
    retention_cleanup_agent,
    retention_timezone,
)
from pii_detector.db.models import DocumentModel, RetentionPolicyModel, UserRoleModel

router = APIRouter(prefix="/settings", tags=["Settings & Retention"])


class RetentionUpdateRequest(BaseModel):
    retention_days: int = Field(..., ge=MIN_RETENTION_DAYS, le=MAX_RETENTION_DAYS)
    owner_id: str = "usr_admin"
    organization_id: str = "org_default"


class RetentionPurgeRequest(BaseModel):
    owner_id: str = "usr_admin"
    organization_id: str = "org_default"


def _require_retention_admin(db, owner_id: str) -> UserRoleModel:
    user = db.query(UserRoleModel).filter(UserRoleModel.user_id == owner_id).first()
    if not user:
        raise HTTPException(status_code=403, detail="Retention administration requires an authorized workspace role")
    permissions = user.get_permissions()
    if user.role not in {"Admin", "Compliance"} and "retention_clean" not in permissions:
        raise HTTPException(status_code=403, detail="Only workspace admins or compliance officers may manage retention")
    return user


def _status(db, organization_id: str) -> Dict[str, Any]:
    policy = retention_cleanup_agent.get_or_create_policy(db, organization_id)
    today = datetime.now(retention_timezone()).date()
    cutoff = cutoff_date_for(policy.retention_days, today)
    documents = db.query(DocumentModel).filter(DocumentModel.organization_id == organization_id).all()
    effective_dates = [local_date_for_timestamp(document.upload_timestamp) for document in documents]
    effective_dates = [value for value in effective_dates if value is not None]
    expired_count = sum(value <= cutoff for value in effective_dates)
    retained_dates = [value for value in effective_dates if value > cutoff]
    oldest = min(retained_dates).isoformat() if retained_dates else None
    db.commit()
    return {
        "retention_days": policy.retention_days,
        "min_days": MIN_RETENTION_DAYS,
        "max_days": MAX_RETENTION_DAYS,
        "timezone": retention_timezone().key,
        "oldest_retained_data": oldest,
        "expired_records_pending_cleanup": expired_count,
        "next_cleanup": next_cleanup_at().isoformat(),
        "last_cleanup_date": policy.last_cleanup_date.isoformat() if policy.last_cleanup_date else None,
    }


@router.get("/retention")
async def get_retention_settings(
    organization_id: str = Query("org_default"),
):
    with db_manager.get_session() as db:
        return _status(db, organization_id)


@router.put("/retention")
async def update_retention_settings(request: RetentionUpdateRequest):
    with db_manager.get_session() as db:
        _require_retention_admin(db, request.owner_id)
        policy = retention_cleanup_agent.get_or_create_policy(db, request.organization_id)
        previous = policy.retention_days
        policy.retention_days = request.retention_days
        policy.updated_at = datetime.utcnow()
        db.commit()
        result = _status(db, request.organization_id)
        result["previous_retention_days"] = previous
        result["warning"] = (
            f"Changing retention from {previous} to {request.retention_days} days may cause older data to be deleted during the next cleanup."
            if request.retention_days < previous else None
        )
        return result


@router.post("/retention/purge-expired")
async def purge_expired_data(request: RetentionPurgeRequest):
    with db_manager.get_session() as db:
        _require_retention_admin(db, request.owner_id)
        summary = retention_cleanup_agent.purge_expired(
            db,
            organization_id=request.organization_id,
            actor_id=request.owner_id,
        )
        summary["message"] = f"Retention cleanup complete. {summary.get('documents_deleted', 0)} expired documents removed."
        return summary
