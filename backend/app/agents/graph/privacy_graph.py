from typing import TypedDict, List, Dict, Any, Optional
import os
import logging
from pathlib import Path

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from pii_detector.agents.pii_detection_agent import PIIDetectionAgent
from pii_detector.agents.classification_agent import ClassificationAgent
from pii_detector.agents.risk_agent import RiskAgent
from pii_detector.agents.dpdp_guardrails import DPDPGuardrailsEngine
from pii_detector.agents.masking_agent import MaskingAgent
from pii_detector.agents.privacy_rag_agent import PrivacyRAGAgent
from pii_detector.agents.audit_log_agent import AuditLogAgent

from app.agents.observability import traceable

logger = logging.getLogger(__name__)

class PrivacyAgentState(TypedDict):
    # Initial document input
    document_id: str
    file_name: str
    file_path: Optional[str]
    raw_text: str

    # Detection outputs
    detected_entities: List[Dict[str, Any]]
    total_count: int
    regex_spacy_count: int
    llm_count: int

    # Classification outputs
    domain: str
    category_scores: Dict[str, int]
    matched_keywords: Dict[str, List[str]]
    classification_confidence: float
    compliance_rule_set: str
    requires_manual_override: bool

    # Risk outputs
    risk_score: float
    risk_category: str
    route_to_hitl: bool
    entity_type_counts: Dict[str, int]

    # DPDP outputs
    dpdp_compliant: bool
    dpdp_violations: List[str]
    dpdp_passed_rules: List[str]
    dpdp_recommendations: List[str]
    dpdp_guardrail_status: Dict[str, bool]

    # HITL
    approved_entities: List[Dict[str, Any]]
    hitl_approved: bool
    hitl_review_completed: bool

    # Masking
    masked_text: str
    token_mapping: Dict[str, str]

    # Cloud safety
    cloud_transmission_safe: bool
    cloud_leakages: List[Dict[str, Any]]

    # De-masking (Separate explicit authorization state)
    demasking_requested: bool
    demasking_approved: bool
    demasking_status: str
    demasked_text: Optional[str]

    # RAG / Audit
    rag_indexed: bool
    audit_logged: bool

    status: str


@traceable(name="read_and_detect_node", run_type="chain")
def read_and_detect_node(state: PrivacyAgentState) -> Dict[str, Any]:
    """Node 1: Runs DocumentReader and PIIDetector to extract text and PII candidates."""
    logger.info(f"[LangGraph Node] Running PII Detection for doc: {state.get('document_id')}")
    has_file = bool(state.get("file_path") and os.path.exists(state["file_path"]))
    agent = PIIDetectionAgent(enable_ocr=has_file, enable_llm_residual=False)

    if has_file:
        res = agent.process_file_on_the_go(state["file_path"])
    else:
        res = agent.process_text_on_the_go(state.get("raw_text", ""))

    return {
        "raw_text": res.get("raw_text", ""),
        "detected_entities": res.get("detected_entities", []),
        "total_count": res.get("total_count", 0),
        "regex_spacy_count": res.get("regex_spacy_count", 0),
        "llm_count": res.get("llm_count", 0),
        "status": "detected"
    }


@traceable(name="classify_document_node", run_type="chain")
def classify_document_node(state: PrivacyAgentState) -> Dict[str, Any]:
    """Node 2: Classifies document category and compliance rule set."""
    logger.info("[LangGraph Node] Running Classification Agent")
    agent = ClassificationAgent()
    res = agent.classify_document(state.get("raw_text", ""))
    return {
        "domain": res["category"],
        "category_scores": res["category_scores"],
        "matched_keywords": res["matched_keywords"],
        "classification_confidence": res["confidence_score"],
        "compliance_rule_set": res["compliance_rule_set"],
        "requires_manual_override": res["requires_manual_override"],
        "status": "classified"
    }


@traceable(name="evaluate_risk_node", run_type="chain")
def evaluate_risk_node(state: PrivacyAgentState) -> Dict[str, Any]:
    """Node 3: Evaluates privacy risk score and category."""
    logger.info("[LangGraph Node] Running Risk Assessment Agent")
    agent = RiskAgent()
    domain = state.get("domain", "General")
    res = agent.evaluate_risk(domain, state.get("detected_entities", []))
    return {
        "risk_score": res["risk_score"],
        "risk_category": res["risk_category"],
        "route_to_hitl": res["route_to_hitl"],
        "entity_type_counts": res["entity_type_counts"],
        "status": "risk_evaluated"
    }


@traceable(name="evaluate_dpdp_node", run_type="chain")
def evaluate_dpdp_node(state: PrivacyAgentState) -> Dict[str, Any]:
    """Node 4: Evaluates DPDP Act 2023 / 2025 rules."""
    logger.info("[LangGraph Node] Running DPDP Guardrails Engine")
    engine = DPDPGuardrailsEngine()
    approved_entities = state.get("approved_entities")
    approved_count = len(approved_entities) if approved_entities is not None else 0
    hitl_completed = state.get("hitl_review_completed", False) or state.get("hitl_approved", False)

    res = engine.evaluate_document_processing(
        raw_text=state.get("raw_text", ""),
        detected_entities=state.get("detected_entities", []),
        human_approved_count=approved_count,
        total_entities_count=state.get("total_count", 0),
        hitl_review_completed=hitl_completed,
        domain=state.get("domain", "General"),
        compliance_rule_set=state.get("compliance_rule_set", "STANDARD_PRIVACY_RULES"),
        cloud_transmission_safe=state.get("cloud_transmission_safe"),
        audit_logged=state.get("audit_logged")
    )
    return {
        "dpdp_compliant": res.is_compliant,
        "dpdp_violations": res.violations,
        "dpdp_passed_rules": res.passed_rules,
        "dpdp_recommendations": res.recommendations,
        "dpdp_guardrail_status": res.guardrail_status,
        "status": "dpdp_evaluated"
    }


@traceable(name="hitl_review_node", run_type="chain")
def hitl_review_node(state: PrivacyAgentState) -> Dict[str, Any]:
    """Node 5: Human-In-The-Loop review node."""
    logger.info("[LangGraph Node] Waiting for human approval")

    approved_entities = state.get("approved_entities")
    hitl_completed = state.get("hitl_review_completed", False)

    if not hitl_completed and approved_entities is None:
        logger.info("No human approval received yet. HITL review is required.")
        return {
            "hitl_approved": False,
            "hitl_review_completed": False,
            "status": "waiting_for_human_approval"
        }

    # Human has explicitly provided the approved entities
    approved_list = approved_entities if approved_entities is not None else []
    logger.info(f"Human approved {len(approved_list)} entities")

    return {
        "approved_entities": approved_list,
        "hitl_approved": len(approved_list) > 0,
        "hitl_review_completed": True,
        "status": "hitl_approved"
    }


@traceable(name="apply_masking_node", run_type="chain")
def apply_masking_node(state: PrivacyAgentState) -> Dict[str, Any]:
    """Node 6: Applies fail-closed masking only to human-approved entities."""
    logger.info("[LangGraph Node] Running Masking Agent")

    approved_entities = state.get("approved_entities")

    if approved_entities is None:
        if state.get("total_count", 0) == 0:
            approved_entities = []
        else:
            raise ValueError(
                "Cannot mask document: human approval has not been completed."
            )

    agent = MaskingAgent(token_format="<{label}_{id}>")

    masked_res = agent.apply_hitl_masking(
        state.get("raw_text", ""),
        approved_entities
    )

    return {
        "masked_text": masked_res.masked_text,
        "token_mapping": masked_res.mapping,
        "status": "masked"
    }


@traceable(name="cloud_leakage_check_node", run_type="chain")
def cloud_leakage_check_node(state: PrivacyAgentState) -> Dict[str, Any]:
    """Node 7: Validates zero raw PII leakage before cloud transmission / RAG ingestion."""
    logger.info("[LangGraph Node] Running Pre-Cloud Transmission Leakage Check")
    engine = DPDPGuardrailsEngine()
    result = engine.evaluate_cloud_transmission(
        state.get("masked_text", ""),
        state.get("token_mapping", {})
    )

    return {
        "cloud_transmission_safe": result["is_safe"],
        "cloud_leakages": result["leakages_found"],
        "status": "cloud_safe" if result["is_safe"] else "cloud_transmission_blocked"
    }


@traceable(name="rag_ingestion_node", run_type="chain")
def rag_ingestion_node(state: PrivacyAgentState) -> Dict[str, Any]:
    """Node 8: Ingests masked text into vector store / RAG agent."""
    logger.info("[LangGraph Node] Running RAG Ingestion Agent")
    try:
        agent = PrivacyRAGAgent()
        if hasattr(agent, "ingest_masked_text"):
            agent.ingest_masked_text(masked_text=state.get("masked_text", ""), document_id=state.get("document_id"))
        elif hasattr(agent, "ingest_masked_result"):
            agent.ingest_masked_result(masked_result=state.get("masked_text", ""), document_id=state.get("document_id"))
        else:
            logger.warning("RAG ingestion notice in LangGraph")
            return {"rag_indexed": False, "status": "rag_indexing_notice"}
        return {"rag_indexed": True, "status": "rag_indexed"}
    except Exception as e:
        logger.warning(f"RAG ingestion notice in LangGraph: {e}")
        return {"rag_indexed": False, "status": "rag_indexing_notice"}


@traceable(name="log_audit_node", run_type="chain")
def log_audit_node(state: PrivacyAgentState) -> Dict[str, Any]:
    """Node 9: Generates an immutable, hash-chained audit log entry without raw PII."""
    logger.info("[LangGraph Node] Running Audit Log Agent")
    try:
        agent = AuditLogAgent()
        res = agent.log_event(
            agent_name="LangGraphPrivacyWorkflow",
            action_type="GRAPH_EXECUTION",
            actor_id="usr_admin",
            document_id=state.get("document_id", "doc_graph"),
            dpdp_compliant=state.get("dpdp_compliant", True),
            hitl_approved=state.get("hitl_approved", False),
            demasking_approved=state.get("demasking_approved", False),
            details={
                "risk_score": state.get("risk_score"),
                "risk_category": state.get("risk_category"),
                "domain": state.get("domain"),
                "total_entities": state.get("total_count", 0),
                "approved_entities_count": len(state.get("approved_entities", [])),
                "total_masked_tokens": len(state.get("token_mapping", {})),
                "dpdp_compliant": state.get("dpdp_compliant"),
                "cloud_transmission_safe": state.get("cloud_transmission_safe", True),
                "status": state.get("status")
            }
        )
        persisted = res.get("persisted", True)
        return {
            "audit_logged": persisted,
            "status": ("completed" if state.get("cloud_transmission_safe", True) else "completed_blocked_leakage") if persisted else "completed_with_audit_notice"
        }
    except Exception as e:
        logger.warning(f"Audit log notice in LangGraph: {e}")
        return {"audit_logged": False, "status": "completed_with_audit_notice"}



def route_after_compliance_eval(state: PrivacyAgentState) -> str:
    """Conditional edge router: routes high risk, manual override, or pending approval to hitl_review."""
    needs_hitl = (
        state.get("route_to_hitl")
        or state.get("risk_category") == "High"
        or state.get("requires_manual_override")
        or not state.get("dpdp_compliant")
    )
    if needs_hitl:
        if not state.get("hitl_review_completed"):
            return "hitl_review"
    return "apply_masking"


def route_after_cloud_leakage_check(state: PrivacyAgentState) -> str:
    """Conditional edge router: blocks RAG cloud ingestion if leakage is detected."""
    if state.get("cloud_transmission_safe", True):
        return "rag_ingestion"
    return "log_audit"


def create_privacy_graph(checkpointer: Optional[Any] = None):
    """
    Constructs and compiles the multi-agent PrivacyShield StateGraph workflow.
    """
    workflow = StateGraph(PrivacyAgentState)

    # Add agent nodes
    workflow.add_node("read_and_detect", read_and_detect_node)
    workflow.add_node("classify_document", classify_document_node)
    workflow.add_node("evaluate_risk", evaluate_risk_node)
    workflow.add_node("evaluate_dpdp", evaluate_dpdp_node)
    workflow.add_node("hitl_review", hitl_review_node)
    workflow.add_node("apply_masking", apply_masking_node)
    workflow.add_node("cloud_leakage_check", cloud_leakage_check_node)
    workflow.add_node("rag_ingestion", rag_ingestion_node)
    workflow.add_node("log_audit", log_audit_node)

    # Define linear & conditional edges
    workflow.set_entry_point("read_and_detect")
    workflow.add_edge("read_and_detect", "classify_document")
    workflow.add_edge("classify_document", "evaluate_risk")
    workflow.add_edge("evaluate_risk", "evaluate_dpdp")

    # Conditional routing after DPDP / Risk evaluation
    workflow.add_conditional_edges(
        "evaluate_dpdp",
        route_after_compliance_eval,
        {
            "hitl_review": "hitl_review",
            "apply_masking": "apply_masking"
        }
    )

    workflow.add_edge("hitl_review", "apply_masking")
    workflow.add_edge("apply_masking", "cloud_leakage_check")

    # Conditional routing after Cloud Leakage Safety Check
    workflow.add_conditional_edges(
        "cloud_leakage_check",
        route_after_cloud_leakage_check,
        {
            "rag_ingestion": "rag_ingestion",
            "log_audit": "log_audit"
        }
    )

    workflow.add_edge("rag_ingestion", "log_audit")
    workflow.add_edge("log_audit", END)

    if checkpointer is None:
        checkpointer = MemorySaver()

    app_graph = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["hitl_review"]
    )

    return app_graph
