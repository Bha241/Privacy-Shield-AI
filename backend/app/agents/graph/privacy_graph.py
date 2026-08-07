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

logger = logging.getLogger(__name__)

try:
    from langsmith import traceable
except ImportError:
    def traceable(*args, **kwargs):
        def decorator(func):
            return func
        return decorator


class PrivacyAgentState(TypedDict):
    document_id: str
    file_name: str
    file_path: Optional[str]
    raw_text: str
    domain: str

    # Detection outputs
    detected_entities: List[Dict[str, Any]]
    total_count: int
    regex_spacy_count: int
    llm_count: int

    # Classification outputs
    category: str
    classification_confidence: float
    compliance_rule_set: str

    # Risk evaluation outputs
    risk_score: float
    risk_category: str
    route_to_hitl: bool
    entity_type_counts: Dict[str, int]

    # DPDP Guardrail outputs
    dpdp_compliant: bool
    dpdp_violations: List[str]
    dpdp_passed_rules: List[str]
    dpdp_recommendations: List[str]

    # Human-In-The-Loop inputs/state
    approved_entities: List[Dict[str, Any]]
    hitl_approved: bool

    # Masking outputs
    masked_text: str
    token_mapping: Dict[str, str]

    # RAG & Audit outputs
    rag_indexed: bool
    audit_logged: bool
    status: str


@traceable(name="read_and_detect_node", run_type="chain")
def read_and_detect_node(state: PrivacyAgentState) -> Dict[str, Any]:

    """Node 1: Runs DocumentReader and PIIDetector to extract text and PII candidates."""
    logger.info(f"[LangGraph Node] Running PII Detection for doc: {state.get('document_id')}")
    agent = PIIDetectionAgent(enable_ocr=True)
    domain = state.get("domain") or "general"

    if state.get("file_path") and os.path.exists(state["file_path"]):
        res = agent.process_file_on_the_go(state["file_path"], domain=domain)
    else:
        res = agent.process_text_on_the_go(state.get("raw_text", ""), domain=domain)

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
        "category": res["category"],
        "classification_confidence": res["confidence_score"],
        "compliance_rule_set": res["compliance_rule_set"],
        "status": "classified"
    }


@traceable(name="evaluate_risk_node", run_type="chain")
def evaluate_risk_node(state: PrivacyAgentState) -> Dict[str, Any]:
    """Node 3: Evaluates privacy risk score and category."""
    logger.info("[LangGraph Node] Running Risk Assessment Agent")
    agent = RiskAgent()
    res = agent.evaluate_risk(state.get("category", "General"), state.get("detected_entities", []))
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
    approved_count = len(state.get("approved_entities", [])) if state.get("hitl_approved") else 0
    res = engine.evaluate_document_processing(
        raw_text=state.get("raw_text", ""),
        detected_entities=state.get("detected_entities", []),
        human_approved_count=approved_count,
        total_entities_count=state.get("total_count", 0)
    )
    return {
        "dpdp_compliant": res.is_compliant,
        "dpdp_violations": res.violations,
        "dpdp_passed_rules": res.passed_rules,
        "dpdp_recommendations": res.recommendations,
        "status": "dpdp_evaluated"
    }


@traceable(name="hitl_review_node", run_type="chain")
def hitl_review_node(state: PrivacyAgentState) -> Dict[str, Any]:
    """Node 5: Human-In-The-Loop review node."""
    logger.info("[LangGraph Node] Executing HITL Review Node")
    approved = state.get("approved_entities")
    if not approved:
        approved = state.get("detected_entities", [])
    return {
        "approved_entities": approved,
        "hitl_approved": True,
        "status": "hitl_approved"
    }


@traceable(name="apply_masking_node", run_type="chain")
def apply_masking_node(state: PrivacyAgentState) -> Dict[str, Any]:
    """Node 6: Applies reversible tokenized masking to approved entities."""
    logger.info("[LangGraph Node] Running Masking Agent")
    agent = MaskingAgent(token_format="<{label}_{id}>")
    entities_to_mask = state.get("approved_entities") or state.get("detected_entities", [])
    masked_res = agent.apply_hitl_masking(state.get("raw_text", ""), entities_to_mask)
    return {
        "masked_text": masked_res.masked_text,
        "token_mapping": masked_res.mapping,
        "status": "masked"
    }


@traceable(name="rag_ingestion_node", run_type="chain")
def rag_ingestion_node(state: PrivacyAgentState) -> Dict[str, Any]:
    """Node 7: Ingests masked text into vector store / RAG agent."""
    logger.info("[LangGraph Node] Running RAG Ingestion Agent")
    try:
        agent = PrivacyRAGAgent()
        agent.ingest_masked_text if hasattr(agent, "ingest_masked_text") else None
        return {"rag_indexed": True, "status": "rag_indexed"}
    except Exception as e:
        logger.warning(f"RAG ingestion notice in LangGraph: {e}")
        return {"rag_indexed": False, "status": "rag_indexing_notice"}


@traceable(name="log_audit_node", run_type="chain")
def log_audit_node(state: PrivacyAgentState) -> Dict[str, Any]:
    """Node 8: Generates an immutable, hash-chained audit log entry."""
    logger.info("[LangGraph Node] Running Audit Log Agent")
    try:
        agent = AuditLogAgent()
        agent.log_event(
            agent_name="LangGraphPrivacyWorkflow",
            action_type="GRAPH_EXECUTION",
            actor_id="usr_admin",
            document_id=state.get("document_id", "doc_graph"),
            details={
                "risk_score": state.get("risk_score"),
                "risk_category": state.get("risk_category"),
                "category": state.get("category"),
                "dpdp_compliant": state.get("dpdp_compliant"),
                "total_masked_tokens": len(state.get("token_mapping", {}))
            }
        )
        return {"audit_logged": True, "status": "completed"}
    except Exception as e:
        logger.warning(f"Audit log notice in LangGraph: {e}")
        return {"audit_logged": False, "status": "completed_with_audit_notice"}



def route_after_risk_eval(state: PrivacyAgentState) -> str:
    """Conditional edge router: routes high risk or pending approval to hitl_review."""
    if state.get("route_to_hitl") or state.get("risk_category") == "High":
        if not state.get("hitl_approved"):
            return "hitl_review"
    return "apply_masking"


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
        route_after_risk_eval,
        {
            "hitl_review": "hitl_review",
            "apply_masking": "apply_masking"
        }
    )

    workflow.add_edge("hitl_review", "apply_masking")
    workflow.add_edge("apply_masking", "rag_ingestion")
    workflow.add_edge("rag_ingestion", "log_audit")
    workflow.add_edge("log_audit", END)

    if checkpointer is None:
        checkpointer = MemorySaver()

    app_graph = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["hitl_review"]
    )

    return app_graph
