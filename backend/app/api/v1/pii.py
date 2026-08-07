import sys
import time
import re
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.schemas.pii import (
    PIIRedactRequest,
    PIIRedactResponse,
    EntityMatch,
    DocumentClassification,
    ChatMessageRequest,
    ChatMessageResponse,
    LLMSettings
)

logger = logging.getLogger(__name__)

# -------------------------------------------------
# Add agents path
# -------------------------------------------------
agents_base_dir = Path(__file__).resolve().parent.parent.parent / "agents"
if str(agents_base_dir) not in sys.path:
    sys.path.insert(0, str(agents_base_dir))

# -------------------------------------------------
# Load agents
# -------------------------------------------------
try:
    from app.agents.agents.classification_agent import ClassificationAgent
    from app.agents.agents.risk_agent import RiskAgent
    from app.agents.agents.masking_agent import MaskingAgent
    from app.agents.agents.demasking_agent import DemaskingAgent
    from app.agents.agents.audit_log_agent import AuditLogAgent
    from app.agents.agents.dpdp_guardrails import DPDPGuardrailsEngine
    from app.agents.agents.pii_detection_agent import PIIDetectionAgent   # if available

    classification_agent = ClassificationAgent()
    risk_agent = RiskAgent()
    masking_agent = MaskingAgent()
    demasking_agent = DemaskingAgent()
    audit_agent = AuditLogAgent()
    dpdp_guardrails = DPDPGuardrailsEngine()
    try:
        detection_agent = PIIDetectionAgent()
    except:
        detection_agent = None
    AGENT_PIPELINE_LOADED = True
except Exception as err:
    print(f"[Info] Multi-agent core initializing with pattern fallback: {err}")
    classification_agent = None
    risk_agent = None
    masking_agent = None
    demasking_agent = None
    audit_agent = None
    dpdp_guardrails = None
    detection_agent = None
    AGENT_PIPELINE_LOADED = False

# -------------------------------------------------
# PrivacyRAGAgent
# -------------------------------------------------
try:
    from app.agents.agents.privacy_rag_agent import PrivacyRAGAgent
    rag_agent = PrivacyRAGAgent(model_name="llama-3.3-70b-versatile")
    RAG_AGENT_LOADED = True
    print("[Info] PrivacyRAGAgent loaded successfully")
except Exception as e:
    try:
        from pii_detector.agents.privacy_rag_agent import PrivacyRAGAgent
        rag_agent = PrivacyRAGAgent(model_name="llama-3.3-70b-versatile")
        RAG_AGENT_LOADED = True
        print("[Info] PrivacyRAGAgent loaded from pii_detector")
    except Exception as e2:
        print(f"[Warning] PrivacyRAGAgent not available: {e} / {e2}")
        rag_agent = None
        RAG_AGENT_LOADED = False

router = APIRouter(prefix="/pii", tags=["PII Detection & Redaction"])

# -------------------------------------------------
# Fallback regex
# -------------------------------------------------
PII_PATTERNS = {
    "NAME": r"(?:[•\*\-\s]*\b(?:Full Name|Customer Name|Taxpayer Name|Taxpayer|Name|Signed by|Patient|Applicant|Holder|Student|User|Licensor|Licensee|Recipient|Coordinator|Logistics Coordinator|Dispatch Officer|Officer|Accountant|Manager|Contact|Representative|Primary Representative|Signatory|Physician|Doctor|Executive|Delegate)[:\s]+)([A-Za-z0-9\.\'\-]+\s+[A-Za-z0-9\.\'\-]+(?:\s+[A-Za-z0-9\.\'\-]+)?)|(?:Mr\.|Mrs\.|Ms\.|Shri|Smt|Dr\.|Prof\.|son/daughter of|s/o|d/o|w/o|c/o)[:\s]+([A-Z][a-zA-Z\.\'\-]+\s+[A-Z][a-zA-Z\.\'\-]+)",
    "AADHAAR": r"(?:\b\d{4}[-.\s]?\d{4}[-.\s]?\d{4}\b|\b\(\d{4}\)[-.\s]?\d{4}[-.\s]?\d{4}\b)",
    "PAN": r"\b[A-Za-z]{5}\s?[0-9]{4}\s?[A-Za-z]\b|\b[A-Za-z]{3,5}[0-9]{4}[A-Za-z]\b",
    "TAX_ID": r"\b(?:Taxpan|Tax\s*PAN|Tax\s*ID|PAN\s*ID|TIN|EIN)[:\s]+[A-Za-z0-9\-]{8,15}\b",
    "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "PHONE": r"(?:\+?\d{1,4}[-.\s]?)?(?:\(\d{2,5}\)[-.\s]?)?\b\d{3,5}[-.\s]?\d{3,5}\b|\b(?:\+?91[-.\s]?)?[5-9]\d{8,9}\b|\b(?:\+?\d{1,3}[-.\s]?)?\d{9,11}\b|\b(?:\+?91[-.\s]?)?\d{1,4}[X*]{2,8}\d{1,4}\b",
    "GSTIN": r"\b\d{2}[A-Za-z]{5}\d{4}[A-Za-z]{1}[A-Za-z0-9]{1}[Zz]{1}[A-Za-z0-9]{1}\b",
    "CREDIT_CARD": r"\b(?:\d{4}[- ]?){3}\d{4}\b|\bxxxx[- ]?xxxx[- ]?xxxx[- ]?\d{4}\b",
}


# ============================================================
# Helper Schemas for HITL
# ============================================================

class EntityCandidate(BaseModel):
    id: Optional[int] = None
    text: str
    label: str
    start: int = 0
    end: int = 0
    confidence: float = 0.95
    approved: bool = True
    user_custom_label: Optional[str] = None


class MaskRequest(BaseModel):
    document_id: str
    original_text: str
    approved_entities: List[EntityCandidate]
    actor_id: str = "usr_system"
    force_mask: bool = False


class MaskResponse(BaseModel):
    status: str
    document_id: str
    masked_text: str
    mapping: Dict[str, str]
    risk_score: float
    risk_level: str
    category: str
    requires_hitl: bool
    dpdp_compliant: bool
    ingested: bool
    message: str


# ============================================================
# /redact  → Detection + Classification + Risk (HITL decision)
# ============================================================

@router.post("/redact", response_model=PIIRedactResponse)
async def redact_pii(request: PIIRedactRequest):
    text = (request.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    matches: List[EntityMatch] = []
    masked_result = None
    redacted_text = text

    # ---------- 1. Detect ----------
    if RAG_AGENT_LOADED and rag_agent:
        try:
            detection = rag_agent.detector.detect(text)
            for ent in detection.all_entities:
                matches.append(EntityMatch(
                    entity_type=getattr(ent, "label", "UNKNOWN"),
                    text=getattr(ent, "text", ""),
                    start=getattr(ent, "start", 0),
                    end=getattr(ent, "end", 0),
                    score=getattr(ent, "score", 0.95)
                ))
            masked_result = rag_agent.masker.mask(text, detection.all_entities)
            redacted_text = masked_result.masked_text
        except Exception as e:
            logger.warning(f"Advanced detector failed: {e}")

    if not matches:
        # Fallback regex
        for entity_type, pattern in PII_PATTERNS.items():
            for m in re.finditer(pattern, text, re.IGNORECASE):
                matches.append(EntityMatch(
                    entity_type=entity_type,
                    text=m.group(0),
                    start=m.start(),
                    end=m.end(),
                    score=0.92
                ))
        # Deduplicate overlaps
        matches = sorted(matches, key=lambda x: (x.start, -len(x.text)))
        filtered = []
        last_end = -1
        for m in matches:
            if m.start >= last_end:
                filtered.append(m)
                last_end = m.end
        matches = filtered
        redacted_text = apply_masking(text, matches) if matches else text

    # ---------- 2. Classification ----------
    if classification_agent:
        class_res = classification_agent.classify_document(text)
        category_name = class_res.get("category", "General")
        confidence_val = class_res.get("confidence_score", 0.85)
        compliance_rules = [class_res.get("compliance_rule_set", "DPDP_ACT_2025_RULES"), "GDPR Art. 9"]
        summary_desc = f"Classified as {category_name} ({int(confidence_val*100)}% confidence)"
    else:
        lower_t = text.lower()
        if any(k in lower_t for k in ["patient", "diagnosis", "hospital", "medical", "clinical"]):
            category_name = "Medical"
        elif any(k in lower_t for k in ["pan", "invoice", "bank", "gst", "tax", "salary"]):
            category_name = "Financial"
        else:
            category_name = "General"
        confidence_val = 0.88
        compliance_rules = ["DPDP Act 2023", "GDPR Art. 9"]
        summary_desc = f"Classified as {category_name}"

    classification = DocumentClassification(
        category=category_name,
        sensitivity="RESTRICTED / HIGH" if category_name in ["Medical", "Financial"] else "CONFIDENTIAL",
        confidence=confidence_val,
        summary=summary_desc,
        compliance_frameworks=compliance_rules
    )

    # ---------- 3. Risk + HITL decision ----------
    dict_entities = [{"label": m.entity_type, "text": m.text} for m in matches]
    if risk_agent:
        risk_res = risk_agent.evaluate_risk(category_name, dict_entities)
        risk_score = risk_res.get("risk_score", 0)
        risk_level = risk_res.get("risk_category", "Low").upper()
        requires_hitl = risk_res.get("route_to_hitl", False)
    else:
        risk_score = min(len(matches) * 22, 100)
        risk_level = "HIGH" if risk_score >= 50 else "MEDIUM" if risk_score >= 25 else "LOW"
        requires_hitl = risk_level in ["HIGH", "CRITICAL"] or category_name in ["Medical", "Financial"]

    # Force HITL for sensitive cases
    if category_name in ["Medical", "Financial"] or risk_level in ["HIGH", "CRITICAL"]:
        requires_hitl = True

    # ---------- 4. Audit ----------
    if audit_agent:
        try:
            audit_agent.log_event(
                agent_name="RedactPipeline",
                action_type="DETECTION",
                details={
                    "entity_count": len(matches),
                    "risk_score": risk_score,
                    "risk_level": risk_level,
                    "category": category_name,
                    "requires_hitl": requires_hitl
                },
                document_id=getattr(request, "document_id", None)
            )
        except Exception:
            pass

    # Note: We do NOT auto-ingest into RAG here if HITL is required.
    # Ingestion happens only after /mask with approved entities.

    return PIIRedactResponse(
        original_text=text,
        redacted_text=redacted_text,
        entities=matches,
        risk_score=risk_score,
        risk_level=risk_level,
        compliance_passed=risk_score < 75,
        classification=classification,
        # Extra fields your schema may need to accept (add them if necessary)
        # requires_hitl=requires_hitl  
    )


# ============================================================
# /mask  → Apply HITL approved entities + Ingest into RAG
# ============================================================

@router.post("/mask", response_model=MaskResponse)
async def apply_hitl_mask(request: MaskRequest):
    if not request.approved_entities:
        raise HTTPException(400, "No entities provided")

    approved = [e.dict() for e in request.approved_entities]
    approved_count = sum(1 for e in approved if e.get("approved", True))

    # Re-evaluate risk with approved entities
    class_res = classification_agent.classify_document(request.original_text) if classification_agent else {"category": "General"}
    category = class_res.get("category", "General")

    risk_res = risk_agent.evaluate_risk(category, approved) if risk_agent else {"risk_score": 0, "risk_category": "Low", "route_to_hitl": False}
    risk_score = risk_res.get("risk_score", 0)
    risk_level = risk_res.get("risk_category", "Low").upper()
    requires_hitl = risk_res.get("route_to_hitl", False) or risk_level in ["HIGH", "CRITICAL"]

    # Enforce HITL
    if requires_hitl and approved_count == 0 and not request.force_mask:
        raise HTTPException(
            status_code=403,
            detail="Human-in-the-Loop approval is mandatory for this document. Approve entities first."
        )

    # Apply masking
    if masking_agent:
        masked_result = masking_agent.apply_hitl_masking(request.original_text, approved)
        masked_text = masked_result.masked_text
        mapping = masked_result.mapping
    else:
        # Fallback
        ents = [EntityMatch(entity_type=e["label"], text=e["text"], start=e.get("start",0), end=e.get("end",0), score=0.9) for e in approved if e.get("approved", True)]
        masked_text = apply_masking(request.original_text, ents)
        mapping = create_placeholder_map(ents)

    # DPDP check
    dpdp_ok = True
    if dpdp_guardrails:
        try:
            compliance = dpdp_guardrails.evaluate_document_processing(
                raw_text=request.original_text,
                detected_entities=approved,
                human_approved_count=approved_count,
                total_entities_count=len(approved)
            )
            dpdp_ok = compliance.is_compliant
        except Exception:
            pass

    # Ingest into RAG (only masked content)
    ingested = False
    if RAG_AGENT_LOADED and rag_agent:
        try:
            # Create a simple MaskedResult-like object
            class SimpleMasked:
                def __init__(self, text, mapping):
                    self.masked_text = text
                    self.mapping = mapping
            rag_agent.ingest_masked_result(
                masked_result=SimpleMasked(masked_text, mapping),
                file_name=request.document_id,
                document_id=request.document_id
            )
            ingested = True
        except Exception as e:
            logger.warning(f"RAG ingest failed: {e}")

    # Audit
    if audit_agent:
        try:
            audit_agent.log_event(
                agent_name="MaskingAgent",
                action_type="MASKING",
                details={
                    "document_id": request.document_id,
                    "approved_count": approved_count,
                    "risk_score": risk_score,
                    "ingested": ingested,
                    "dpdp_compliant": dpdp_ok
                },
                actor_id=request.actor_id,
                document_id=request.document_id,
                user_approved=True
            )
        except Exception:
            pass

    return MaskResponse(
        status="success",
        document_id=request.document_id,
        masked_text=masked_text,
        mapping=mapping,
        risk_score=risk_score,
        risk_level=risk_level,
        category=category,
        requires_hitl=requires_hitl,
        dpdp_compliant=dpdp_ok,
        ingested=ingested,
        message="Document masked successfully. Ready for privacy-preserving chat."
    )


# ============================================================
# /chat  → Real PrivacyRAGAgent
# ============================================================

@router.post("/chat", response_model=ChatMessageResponse)
async def chat_rag(request: ChatMessageRequest):
    start_t = time.time()
    user_msg = (request.message or "").strip()
    if not user_msg:
        raise HTTPException(400, "Message cannot be empty")

    llm_settings = request.llm_settings or LLMSettings()
    document_id = getattr(request, "document_id", None) or "doc_default"

    if not RAG_AGENT_LOADED or not rag_agent:
        raise HTTPException(503, "PrivacyRAGAgent is not available")

    try:
        result = rag_agent.answer_query(
            user_query=user_msg,
            document_id=document_id,
            temperature=llm_settings.temperature if llm_settings.temperature is not None else 0.2,
            max_tokens=llm_settings.max_tokens or 512,
            top_p=getattr(llm_settings, "top_p", 0.95),
            model_name=llm_settings.model,
            history=getattr(request, "history", None),
            top_k=4
        )

        proc_time = int((time.time() - start_t) * 1000)

        if audit_agent:
            try:
                audit_agent.log_event(
                    agent_name="PrivacyRAGAgent",
                    action_type="QNA_QUERY",
                    details={
                        "document_id": document_id,
                        "question_preview": user_msg[:100],
                        "model": result.get("model_used"),
                        "processing_ms": proc_time
                    },
                    document_id=document_id
                )
            except Exception:
                pass

        return ChatMessageResponse(
            masked_response=result["masked_response"],
            demasked_response=result["final_unmasked_answer"],
            sources_retrieved=result.get("sources_retrieved", ["vector_store"]),
            model_used=result.get("model_used", "llama-3.3-70b-versatile"),
            processing_time_ms=proc_time
        )

    except Exception as e:
        logger.exception("Chat failed")
        raise HTTPException(500, f"Chat failed: {str(e)}")


# Helper functions kept for fallback
def create_placeholder_map(entities: List[EntityMatch]) -> Dict[str, str]:
    return {f"<{e.entity_type}_{i}>": e.text for i, e in enumerate(entities, 1)}

def apply_masking(text: str, entities: List[EntityMatch]) -> str:
    sorted_ents = sorted(entities, key=lambda x: len(x.text), reverse=True)
    result = text
    for i, ent in enumerate(sorted_ents, 1):
        result = result.replace(ent.text, f"<{ent.entity_type}_{i}>")
    return result

def demask_text(text: str, placeholder_map: Dict[str, str]) -> str:
    result = text
    for ph, orig in sorted(placeholder_map.items(), key=lambda x: len(x[0]), reverse=True):
        result = result.replace(ph, orig)
    return result