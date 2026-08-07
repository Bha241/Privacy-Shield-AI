from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.pii import router as pii_router
from app.api.v1.documents import router as docs_router
from app.api.v1.audit import router as audit_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(pii_router)
api_v1_router.include_router(docs_router)
api_v1_router.include_router(audit_router)
