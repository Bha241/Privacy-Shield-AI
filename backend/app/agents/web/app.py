from pathlib import Path
import os
import shutil
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from pii_detector.agents.classification_agent import ClassificationAgent
from pii_detector.agents.pii_detection_agent import PIIDetectionAgent
from pii_detector.agents.risk_agent import RiskAgent
from pii_detector.agents.masking_agent import MaskingAgent
from pii_detector.agents.privacy_rag_agent import PrivacyRAGAgent
from pii_detector.agents.demasking_agent import DemaskingAgent
from pii_detector.agents.dpdp_guardrails import DPDPGuardrailsEngine
from pii_detector.agents.audit_log_agent import AuditLogAgent

from pii_detector.db.database import db_manager, get_db
from pii_detector.db.models import (
    DocumentModel, PIIEntityModel, SanitizedChunkModel, AuditLogEntryModel,
    UserRoleModel, ComplianceRuleSetModel, DocumentStatusEnum, MaskingMethodEnum
)
from pii_detector.db.encryption import encrypted_mapping_store
from pii_detector.db.retention import data_retention_manager
from pii_detector.db.vector_store import vector_store_manager

app = FastAPI(
    title="PrivacyShieldAI PS_v3 Privacy Assistant with DPDP Guardrails & PostgreSQL Subsystem",
    version="3.3.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"

STATIC_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Initialize Database Schema & Seeds
db_manager.init_db()

# Lazy Agent Pipelines
_classification_agent = None
_detection_agent = None
_risk_agent = None
_masking_agent = None
_qna_agent = None
_demasking_agent = None
_dpdp_engine = None
_audit_agent = None


def get_classification_agent():
    global _classification_agent
    if _classification_agent is None:
        _classification_agent = ClassificationAgent()
    return _classification_agent


def get_detection_agent():
    global _detection_agent
    if _detection_agent is None:
        _detection_agent = PIIDetectionAgent(enable_ocr=True)
    return _detection_agent


def get_risk_agent():
    global _risk_agent
    if _risk_agent is None:
        _risk_agent = RiskAgent()
    return _risk_agent


def get_masking_agent():
    global _masking_agent
    if _masking_agent is None:
        _masking_agent = MaskingAgent(token_format="<{label}_{id}>")
    return _masking_agent


def get_qna_agent():
    global _qna_agent
    if _qna_agent is None:
        _qna_agent = PrivacyRAGAgent()
    return _qna_agent


def get_demasking_agent():
    global _demasking_agent
    if _demasking_agent is None:
        _demasking_agent = DemaskingAgent()
    return _demasking_agent


def get_dpdp_engine():
    global _dpdp_engine
    if _dpdp_engine is None:
        _dpdp_engine = DPDPGuardrailsEngine()
    return _dpdp_engine


def get_audit_agent():
    global _audit_agent
    if _audit_agent is None:
        _audit_agent = AuditLogAgent()
    return _audit_agent


# Session State
current_session = {
    "document_id": "",
    "file_name": "",
    "raw_text": "",
    "candidate_entities": [],
    "masked_result": None,
    "dpdp_status": None,
    "mode": "pending"
}


@app.get("/", response_class=HTMLResponse)
def get_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>PrivacyShieldAI PS_v3 Active with DPDP Guardrails & DB Engine</h1>")
    return HTMLResponse(content=index_file.read_text(encoding="utf-8"))


# --- STEP 1: ON-THE-GO PII DETECTION ---
@app.post("/api/detect")
async def detect_pii_on_the_go(
    file: UploadFile = File(...),
    domain: Optional[str] = Form("general")
):
    """
    On-the-go PII detection for uploaded document based on domain selection.
    Persists Document & PII Entity metadata, encrypts original values, and creates hash-chained audit log.
    """
    try:
        saved_path = UPLOAD_DIR / file.filename
        with open(saved_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        res = get_detection_agent().process_file_on_the_go(str(saved_path), domain=domain or "general")
        if res["status"] == "empty":
            raise HTTPException(status_code=400, detail="No readable text found in document.")

        raw_text = res["raw_text"]
        detected_entities = res["detected_entities"]

        # 1. Classification Agent & Risk Agent Execution
        auto_class_res = get_classification_agent().classify_document(raw_text)
        if domain and domain != "general":
            category = domain.replace("_", " ").title()
            category_match = (category.lower() == auto_class_res["category"].lower())
        else:
            category = auto_class_res["category"]
            category_match = True

        risk_res = get_risk_agent().evaluate_risk(category, detected_entities)
        risk_score = risk_res["risk_score"]

        # Create Document Entity in DB
        db = db_manager.get_session()
        document_id = f"doc_{uuid.uuid4().hex[:12]}"

        doc_record = DocumentModel(
            document_id=document_id,
            filename=file.filename,
            category=category,
            risk_score=risk_score,
            status=DocumentStatusEnum.PENDING.value,
            upload_timestamp=datetime.utcnow(),
            owner_id="usr_admin"
        )
        db.add(doc_record)

        # 2. Persist PII Entity Metadata in DB
        raw_mapping = {}
        for idx, e in enumerate(detected_entities, start=1):
            entity_id = f"ent_{uuid.uuid4().hex[:12]}"
            label = e.get("label", "UNKNOWN")
            token = f"<{label}_{idx}>"
            original_val = e.get("text", "")
            raw_mapping[token] = original_val

            pii_rec = PIIEntityModel(
                entity_id=entity_id,
                document_id=document_id,
                type=label,
                offset_start=e.get("start", 0),
                offset_end=e.get("end", 0),
                confidence=float(e.get("confidence", 0.90)),
                masking_method=MaskingMethodEnum.TOKENIZATION.value
            )
            db.add(pii_rec)

        db.commit()
        db.close()

        # 3. Store Encrypted Mapping for Original Values
        encrypted_mapping_store.store_document_mapping(document_id, raw_mapping)

        # 4. Record Hash-Chained Audit Log Entry
        get_audit_agent().log_event(
            agent_name="PIIDetectionAgent",
            action_type="DETECTION",
            actor_id="usr_admin",
            document_id=document_id,
            details={
                "file_name": file.filename,
                "total_entities_detected": len(detected_entities),
                "category": category,
                "risk_score": risk_score
            }
        )

        # Tag file_name on detected entities for single file upload
        for e in detected_entities:
            e["file_name"] = file.filename

        # Check if accumulating into active pending session
        if current_session.get("mode") == "pending_hitl" and current_session.get("raw_text"):
            prev_raw = current_session["raw_text"]
            prev_entities = current_session.get("candidate_entities", [])
            header_str = f"\n\n--- Document: {file.filename} ---\n\n"
            doc_offset = len(prev_raw) + len(header_str)

            combined_raw = prev_raw + header_str + raw_text

            for e in detected_entities:
                e_copy = dict(e)
                e_copy["id"] = len(prev_entities) + 1
                e_copy["start"] = e.get("start", 0) + doc_offset
                e_copy["end"] = e.get("end", 0) + doc_offset
                prev_entities.append(e_copy)

            combined_file_name = f"{current_session.get('file_name', '')}, {file.filename}"
            doc_id = current_session.get("document_id") or document_id
            current_session["document_id"] = doc_id
            current_session["file_name"] = combined_file_name
            current_session["raw_text"] = combined_raw
            current_session["candidate_entities"] = prev_entities
            current_session["domain"] = domain or "general"

            return JSONResponse({
                "status": "success",
                "document_id": doc_id,
                "file_name": combined_file_name,
                "category": category,
                "risk_score": risk_score,
                "raw_text": combined_raw,
                "candidate_entities": prev_entities,
                "total_detected": len(prev_entities),
                "domain": domain or "general"
            })

        current_session["document_id"] = document_id
        current_session["file_name"] = file.filename
        current_session["raw_text"] = raw_text
        current_session["candidate_entities"] = detected_entities
        current_session["mode"] = "pending_hitl"
        current_session["domain"] = domain or "general"

        return JSONResponse({
            "status": "success",
            "document_id": document_id,
            "file_name": file.filename,
            "category": category,
            "risk_score": risk_score,
            "raw_text": raw_text,
            "candidate_entities": detected_entities,
            "total_detected": res["total_count"],
            "domain": domain or "general"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/clear_session")
async def clear_active_session():
    """Resets active workspace session."""
    global current_session
    current_session = {
        "document_id": "",
        "file_name": "",
        "raw_text": "",
        "candidate_entities": [],
        "masked_result": None,
        "dpdp_status": None,
        "mode": "pending"
    }
    qna = get_qna_agent()
    qna.chunks = []
    qna.chunk_embeddings = None
    qna.masked_result = None
    return JSONResponse({"status": "success", "message": "Session reset successfully."})


# --- STEP 2A: HITL VERIFICATION & MASKING ---
@app.post("/api/verify_and_mask")
async def verify_and_mask_hitl(payload: Dict[str, Any] = Body(...)):
    """
    Processes HITL decisions:
    1. Executes Masking Agent for approved entities
    2. Evaluates DPDP Guardrails
    3. Persists Sanitized Chunks into Vector DB
    4. Triggers Data Retention Policy enforcement
    """
    try:
        document_id = payload.get("document_id") or current_session.get("document_id") or f"doc_{uuid.uuid4().hex[:12]}"
        file_name = payload.get("file_name") or current_session.get("file_name", "document.txt")
        raw_text = payload.get("raw_text") or current_session.get("raw_text", "")
        verified_entities = payload.get("entities", [])

        if not raw_text.strip():
            raise HTTPException(status_code=400, detail="No raw text available for masking.")

        # Masking Agent applies verified entities
        masked_res = get_masking_agent().apply_hitl_masking(raw_text, verified_entities)
        current_session["masked_result"] = masked_res
        current_session["mode"] = "masked"

        # Save output files
        file_stem = Path(file_name).stem
        masked_file_path, mapping_file_path = get_masking_agent().save_masked_outputs(
            file_stem=file_stem,
            masked_result=masked_res,
            output_dir=OUTPUT_DIR
        )

        # Database Session Operations
        db = db_manager.get_session()
        try:
            # Update Document status or create document record if missing
            doc_rec = db.query(DocumentModel).filter(DocumentModel.document_id == document_id).first()
            if doc_rec:
                doc_rec.status = DocumentStatusEnum.SANITIZED.value
            else:
                doc_rec = DocumentModel(
                    document_id=document_id,
                    filename=file_name,
                    category="General",
                    risk_score=0.0,
                    status=DocumentStatusEnum.SANITIZED.value
                )
                db.add(doc_rec)
                db.flush()

            # Persist Sanitized Chunk & Dummy Embedding into Vector DB
            dummy_vector = [0.05 * (i % 10) for i in range(128)]
            sanitized_chunk = vector_store_manager.store_sanitized_chunk(
                db_session=db,
                document_id=document_id,
                text=masked_res.masked_text,
                embedding_vector=dummy_vector,
                page_ref="1"
            )

            sanitized_chunk_dict = sanitized_chunk.to_dict()
            sanitized_chunk_id = sanitized_chunk.chunk_id

            # Evaluate DPDP Act 2025 Guardrails
            approved_count = sum(1 for e in verified_entities if e.get("approved", True))
            dpdp_res = get_dpdp_engine().evaluate_document_processing(
                raw_text=raw_text,
                detected_entities=verified_entities,
                human_approved_count=approved_count,
                total_entities_count=len(verified_entities)
            )
            current_session["dpdp_status"] = dpdp_res

            # Execute Post-Sanitization Data Retention Action
            saved_path = str(UPLOAD_DIR / file_name)
            retention_res = data_retention_manager.process_post_sanitization_retention(saved_path, document_id, db)

            db.commit()
        finally:
            db.close()

        # Ingest into QnA RAG Agent
        get_qna_agent().ingest_masked_result(masked_res, file_name=file_name, document_id=document_id)

        # Record Audit Entry
        get_audit_agent().log_event(
            agent_name="MaskingAgent",
            action_type="MASKING",
            actor_id="usr_admin",
            document_id=document_id,
            details={
                "file_name": file_name,
                "approved_entities_count": approved_count,
                "sanitized_chunk_id": sanitized_chunk_id,
                "retention_action": retention_res["action_taken"],
                "dpdp_compliant": dpdp_res.is_compliant
            }
        )

        return JSONResponse({
            "status": "success",
            "document_id": document_id,
            "file_name": file_name,
            "masked_text": masked_res.masked_text,
            "mapping": masked_res.mapping,
            "sanitized_chunk": sanitized_chunk_dict,
            "retention": retention_res,
            "dpdp_evaluation": {
                "is_compliant": dpdp_res.is_compliant,
                "passed_rules": dpdp_res.passed_rules,
                "violations": dpdp_res.violations,
                "guardrail_status": dpdp_res.guardrail_status,
                "recommendations": dpdp_res.recommendations
            }
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- STEP 2B: BYPASS MASKING (EXPLICIT HUMAN DIRECTIVE) ---
@app.post("/api/bypass_masking")
async def bypass_masking_hitl(payload: Dict[str, Any] = Body(...)):
    """
    Processes explicit human directive to proceed without masking:
    1. Ingests raw document text into QnA Agent with empty entity mapping.
    2. Evaluates DPDP Guardrails (logging explicit human bypass decision).
    3. Persists document status as UNMASKED in database.
    """
    try:
        document_id = payload.get("document_id") or current_session.get("document_id") or f"doc_{uuid.uuid4().hex[:12]}"
        file_name = payload.get("file_name") or current_session.get("file_name", "document.txt")
        raw_text = payload.get("raw_text") or current_session.get("raw_text", "")

        if not raw_text.strip():
            raise HTTPException(status_code=400, detail="No raw text available for unmasked ingestion.")

        from pii_detector.masking.pii_masker import MaskedResult
        unmasked_res = MaskedResult(
            masked_text=raw_text,
            mapping={},
            detailed_mapping=[]
        )

        current_session["masked_result"] = unmasked_res
        current_session["mode"] = "unmasked"

        # Update DB Document Status
        db = db_manager.get_session()
        try:
            doc_rec = db.query(DocumentModel).filter(DocumentModel.document_id == document_id).first()
            if doc_rec:
                doc_rec.status = "UNMASKED"
            db.commit()
        finally:
            db.close()

        # Ingest raw text into QnA Agent
        get_qna_agent().ingest_masked_result(unmasked_res, file_name=file_name, document_id=document_id)

        # Audit Event for Masking Bypass
        get_audit_agent().log_event(
            agent_name="HumanOperator",
            action_type="BYPASS_MASKING",
            actor_id="usr_admin",
            document_id=document_id,
            details={
                "file_name": file_name,
                "reason": "Explicit Human Operator directive to proceed without masking"
            }
        )

        return JSONResponse({
            "status": "success",
            "document_id": document_id,
            "file_name": file_name,
            "masked_text": raw_text,
            "mapping": {}
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- STEP 3: PRIVACY RAG QNA & DE-MASKING ---
@app.post("/api/chat")
async def chat_rag_qna(
    query: str = Form(...),
    groq_api_key: Optional[str] = Form(None),
    auto_demask: Optional[bool] = Form(False),
    mask_prompt: Optional[bool] = Form(True),
    temperature: Optional[float] = Form(0.2),
    max_tokens: Optional[int] = Form(512),
    top_p: Optional[float] = Form(0.95),
    model_name: Optional[str] = Form("llama-3.1-8b-instant"),
    history: Optional[str] = Form(None),
    document_id: Optional[str] = Form(None)
):
    qna_agent = get_qna_agent()

    try:
        api_key = groq_api_key if groq_api_key and groq_api_key.strip() else os.environ.get("GROQ_API_KEY")

        parsed_history = []
        if history:
            try:
                parsed_history = json.loads(history)
            except Exception:
                parsed_history = []

        session_domain = current_session.get("domain", "general")
        active_doc_id = document_id or current_session.get("document_id")
        masked_query = query
        prompt_pii_entities = []
        query_mapping = {}

        if mask_prompt:
            # On-the-go PII detection for prompt/pasted query text using active session domain
            detection_res = get_detection_agent().process_text_on_the_go(query, domain=session_domain)
            prompt_pii_entities = detection_res.get("detected_entities", [])
            if prompt_pii_entities:
                masked_res = get_masking_agent().apply_hitl_masking(query, prompt_pii_entities)
                masked_query = masked_res.masked_text
                query_mapping = masked_res.mapping

        # Pre-merge query_mapping into PrivacyRAGAgent masked_result BEFORE calling answer_query
        if not qna_agent.masked_result:
            from pii_detector.masking.pii_masker import MaskedResult
            qna_agent.masked_result = MaskedResult(masked_text="", mapping={}, detailed_mapping=[])

        qna_agent.masked_result.mapping.update(query_mapping)

        # Send query with LLM hyperparameter settings & conversation history
        qna_res = qna_agent.answer_query(
            user_query=masked_query,
            document_id=active_doc_id,
            groq_api_key=api_key,
            temperature=temperature or 0.2,
            max_tokens=max_tokens or 512,
            top_p=top_p or 0.95,
            model_name=model_name or "llama-3.1-8b-instant",
            history=parsed_history
        )

        # Merge mappings (document mapping + prompt query mapping)
        merged_mapping = dict(qna_agent.masked_result.mapping)

        # Evaluate zero-leakage for cloud transmission including prompt query & context
        text_transmitted = f"Query: {masked_query}\nContext: {qna_res.get('masked_context', '')}"
        leakage_check = get_dpdp_engine().evaluate_cloud_transmission(
            text_to_transmit=text_transmitted,
            entity_mapping=merged_mapping
        )

        demask_res = get_demasking_agent().demask_text(
            masked_text=qna_res["masked_response"],
            mapping=merged_mapping,
            user_approved=True
        )

        # Audit Event for Cloud QnA
        get_audit_agent().log_event(
            agent_name="PrivacyRAGAgent",
            action_type="QNA_QUERY",
            actor_id="usr_admin",
            document_id=current_session.get("document_id"),
            details={
                "query": query,
                "masked_query": masked_query,
                "mask_prompt_enabled": mask_prompt,
                "prompt_pii_count": len(prompt_pii_entities),
                "zero_leakage_verified": leakage_check["is_safe"]
            }
        )

        return JSONResponse({
            "status": "success",
            "query": query,
            "masked_query": masked_query,
            "mask_prompt_enabled": mask_prompt,
            "prompt_pii_detected": len(prompt_pii_entities),
            "masked_context": qna_res["masked_context"],
            "masked_response": qna_res["masked_response"],
            "unmasked_response": demask_res["output_text"],
            "mapping": merged_mapping,
            "model": qna_res["model"],
            "dpdp_zero_leakage_verified": leakage_check["is_safe"],
            "leakage_guardrail": leakage_check,
            "auto_demasked": auto_demask
        })
    except Exception as e:
        err_msg = str(e)
        if "403" in err_msg or "Access denied" in err_msg:
            detail = "Groq API Access Denied (403): Please check your network/VPN settings or enter a custom Groq API key in LLM Controls."
            status_code = 403
        else:
            detail = f"Query Execution Error: {err_msg}"
            status_code = 500
        raise HTTPException(status_code=status_code, detail=detail)


@app.post("/api/chat/stream")
async def chat_rag_qna_stream(
    query: str = Form(...),
    groq_api_key: Optional[str] = Form(None),
    auto_demask: Optional[bool] = Form(False),
    mask_prompt: Optional[bool] = Form(True),
    temperature: Optional[float] = Form(0.2),
    max_tokens: Optional[int] = Form(512),
    top_p: Optional[float] = Form(0.95),
    model_name: Optional[str] = Form("llama-3.1-8b-instant"),
    history: Optional[str] = Form(None),
    document_id: Optional[str] = Form(None)
):
    qna_agent = get_qna_agent()

    try:
        api_key = groq_api_key if groq_api_key and groq_api_key.strip() else os.environ.get("GROQ_API_KEY")

        parsed_history = []
        if history:
            try:
                parsed_history = json.loads(history)
            except Exception:
                parsed_history = []

        session_domain = current_session.get("domain", "general")
        active_doc_id = document_id or current_session.get("document_id")
        masked_query = query
        prompt_pii_entities = []
        query_mapping = {}

        if mask_prompt:
            detection_res = get_detection_agent().process_text_on_the_go(query, domain=session_domain)
            prompt_pii_entities = detection_res.get("detected_entities", [])
            if prompt_pii_entities:
                masked_res = get_masking_agent().apply_hitl_masking(query, prompt_pii_entities)
                masked_query = masked_res.masked_text
                query_mapping = masked_res.mapping

        if not qna_agent.masked_result:
            from pii_detector.masking.pii_masker import MaskedResult
            qna_agent.masked_result = MaskedResult(masked_text="", mapping={}, detailed_mapping=[])

        qna_agent.masked_result.mapping.update(query_mapping)

        stream, masked_context, active_model = qna_agent.answer_query_stream(
            user_query=masked_query,
            document_id=active_doc_id,
            groq_api_key=api_key,
            temperature=temperature or 0.2,
            max_tokens=max_tokens or 512,
            top_p=top_p or 0.95,
            model_name=model_name or "llama-3.1-8b-instant",
            history=parsed_history
        )

        merged_mapping = dict(qna_agent.masked_result.mapping)

        async def generate_events():
            start_payload = {
                "event": "start",
                "query": query,
                "masked_query": masked_query,
                "mask_prompt_enabled": mask_prompt,
                "prompt_pii_detected": len(prompt_pii_entities),
                "model": active_model,
                "mapping": merged_mapping,
                "masked_context": masked_context
            }
            yield f"data: {json.dumps(start_payload)}\n\n"

            accumulated_masked = ""
            demask_agent = get_demasking_agent()

            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    delta_text = chunk.choices[0].delta.content
                    accumulated_masked += delta_text
                    
                    unmasked_accum = demask_agent.demask_text(
                        masked_text=accumulated_masked,
                        mapping=merged_mapping,
                        user_approved=True
                    )["output_text"]

                    chunk_payload = {
                        "event": "chunk",
                        "delta": delta_text,
                        "accumulated_masked": accumulated_masked,
                        "accumulated_unmasked": unmasked_accum
                    }
                    yield f"data: {json.dumps(chunk_payload)}\n\n"

            text_transmitted = f"Query: {masked_query}\nContext: {masked_context}"
            leakage_check = get_dpdp_engine().evaluate_cloud_transmission(
                text_to_transmit=text_transmitted,
                entity_mapping=merged_mapping
            )
            final_unmasked = demask_agent.demask_text(
                masked_text=accumulated_masked,
                mapping=merged_mapping,
                user_approved=True
            )["output_text"]

            end_payload = {
                "event": "end",
                "masked_response": accumulated_masked,
                "unmasked_response": final_unmasked,
                "dpdp_zero_leakage_verified": leakage_check["is_safe"],
                "leakage_guardrail": leakage_check,
                "auto_demasked": auto_demask
            }
            yield f"data: {json.dumps(end_payload)}\n\n"

        return StreamingResponse(generate_events(), media_type="text/event-stream")

    except Exception as e:
        err_msg = str(e)
        if "403" in err_msg or "Access denied" in err_msg:
            detail = "Groq API Access Denied (403): Please check your network/VPN settings or enter a custom Groq API key in LLM Controls."
            status_code = 403
        else:
            detail = f"Query Streaming Error: {err_msg}"
            status_code = 500
        raise HTTPException(status_code=status_code, detail=detail)


# ======================================================
# SECTION 4 DATABASE & DATA REQUIREMENTS ENDPOINTS
# ======================================================

@app.get("/api/db/documents")
def list_db_documents():
    """List all persisted document metadata entities (PostgreSQL)."""
    db = db_manager.get_session()
    try:
        docs = db.query(DocumentModel).order_by(DocumentModel.upload_timestamp.desc()).all()
        return JSONResponse({
            "status": "success",
            "db_type": db_manager.db_type,
            "total_documents": len(docs),
            "documents": [d.to_dict() for d in docs]
        })
    finally:
        db.close()


@app.get("/api/db/pii-entities/{document_id}")
def get_document_pii_entities(document_id: str):
    """Retrieve PII Entity metadata (types, offsets, confidence, masking method)."""
    db = db_manager.get_session()
    try:
        entities = db.query(PIIEntityModel).filter(PIIEntityModel.document_id == document_id).all()
        return JSONResponse({
            "status": "success",
            "document_id": document_id,
            "total_entities": len(entities),
            "pii_entities": [e.to_dict() for e in entities]
        })
    finally:
        db.close()


@app.get("/api/db/audit-trail")
def get_audit_trail():
    """Returns hash-chained audit log entries with cryptographic tamper verification."""
    audit_summary = get_audit_agent().get_summary()
    return JSONResponse({
        "status": "success",
        "db_type": db_manager.db_type,
        "audit_summary": audit_summary,
        "logs": get_audit_agent().get_all_logs()
    })


@app.get("/api/db/users-roles")
def get_users_and_roles():
    """List RBAC User and Role entities with assigned permission sets."""
    db = db_manager.get_session()
    try:
        users = db.query(UserRoleModel).all()
        return JSONResponse({
            "status": "success",
            "total_users": len(users),
            "users_roles": [u.to_dict() for u in users]
        })
    finally:
        db.close()


@app.get("/api/db/compliance-rules")
def get_compliance_rules():
    """List active Compliance Rule Sets (DPDP Act 2025, GDPR, HIPAA)."""
    db = db_manager.get_session()
    try:
        rules = db.query(ComplianceRuleSetModel).all()
        return JSONResponse({
            "status": "success",
            "total_rulesets": len(rules),
            "compliance_rule_sets": [r.to_dict() for r in rules]
        })
    finally:
        db.close()


@app.post("/api/db/retention/cleanup")
def trigger_retention_cleanup():
    """Triggers Data Retention Policy Cleanup (30-day raw file purge, 7-year metadata retention)."""
    db = db_manager.get_session()
    try:
        result = data_retention_manager.execute_scheduled_retention_cleanup(db)

        # Log Retention Audit Event
        get_audit_agent().log_event(
            agent_name="DataRetentionManager",
            action_type="RETENTION_CLEANUP",
            actor_id="usr_compliance",
            details=result
        )

        return JSONResponse({
            "status": "success",
            "retention_policy": data_retention_manager.config.to_dict(),
            "cleanup_result": result
        })
    finally:
        db.close()


# --- FILE DOWNLOAD ENDPOINTS ---
@app.get("/api/download/masked/{filename}")
def download_masked(filename: str):
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=str(file_path), filename=filename, media_type="text/plain")


@app.get("/api/download/mapping/{filename}")
def download_mapping(filename: str):
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=str(file_path), filename=filename, media_type="application/json")


# --- LANGGRAPH MULTI-AGENT WORKFLOW ENDPOINTS ---
_privacy_graph_app = None

def get_privacy_graph():
    global _privacy_graph_app
    if _privacy_graph_app is None:
        from pii_detector.graph.privacy_graph import create_privacy_graph
        _privacy_graph_app = create_privacy_graph()
    return _privacy_graph_app


@app.post("/api/graph/process")
async def process_document_with_langgraph(payload: Dict[str, Any] = Body(...)):
    """
    Executes multi-agent document processing using compiled LangGraph StateGraph workflow.
    """
    text = payload.get("text", "")
    file_name = payload.get("file_name", "document.txt")
    doc_id = payload.get("document_id") or f"doc_{uuid.uuid4().hex[:8]}"
    domain = payload.get("domain", "general")

    initial_state = {
        "document_id": doc_id,
        "file_name": file_name,
        "file_path": payload.get("file_path"),
        "raw_text": text,
        "domain": domain,
        "detected_entities": [],
        "approved_entities": [],
        "hitl_approved": False,
        "total_count": 0,
        "regex_spacy_count": 0,
        "llm_count": 0,
        "category": "General",
        "classification_confidence": 0.85,
        "compliance_rule_set": "STANDARD_PRIVACY_RULES",
        "risk_score": 0.0,
        "risk_category": "Low",
        "route_to_hitl": False,
        "entity_type_counts": {},
        "dpdp_compliant": True,
        "dpdp_violations": [],
        "dpdp_passed_rules": [],
        "dpdp_recommendations": [],
        "masked_text": "",
        "token_mapping": {},
        "rag_indexed": False,
        "audit_logged": False,
        "status": "started"
    }

    graph = get_privacy_graph()
    config = {"configurable": {"thread_id": doc_id}}

    try:
        final_state = graph.invoke(initial_state, config=config)
        return JSONResponse({
            "status": "success",
            "execution_mode": "LangGraph_StateGraph",
            "thread_id": doc_id,
            "final_state": final_state
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LangGraph execution error: {str(e)}")


@app.post("/api/graph/resume")
async def resume_langgraph_hitl(payload: Dict[str, Any] = Body(...)):
    """
    Resumes an interrupted LangGraph HITL review node with user approved entities.
    """
    thread_id = payload.get("thread_id")
    if not thread_id:
        raise HTTPException(status_code=400, detail="Missing required field: thread_id")

    approved_entities = payload.get("approved_entities", [])
    graph = get_privacy_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        graph.update_state(config, {"approved_entities": approved_entities, "hitl_approved": True})
        resumed_state = graph.invoke(None, config=config)
        return JSONResponse({
            "status": "success",
            "execution_mode": "LangGraph_Resumed",
            "thread_id": thread_id,
            "final_state": resumed_state
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LangGraph resume error: {str(e)}")
