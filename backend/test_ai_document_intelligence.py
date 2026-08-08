"""
PrivacyShieldAI - AI Document Analyst & Context Orchestrator Unit Test Suite
Validates:
1. Document Overview -> FULL_DOCUMENT (Bypasses vector search completely)
2. Summary -> FULL_DOCUMENT (Bypasses vector search completely)
3. Compliance -> FULL_DOCUMENT (Bypasses vector search completely)
4. Invoice Analysis -> FULL_DOCUMENT (Bypasses vector search completely)
5. PAN Question -> SEMANTIC_RETRIEVAL / VECTOR_SEARCH
6. GST Question -> SEMANTIC_RETRIEVAL / VECTOR_SEARCH
7. Active Document Protection: 'What is in the document?' never returns 'no context provided'.
"""

import sys
from pathlib import Path

# Setup path and pii_detector module alias
backend_dir = Path(__file__).resolve().parent
agents_dir = backend_dir / "app" / "agents"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(agents_dir) not in sys.path:
    sys.path.insert(0, str(agents_dir))

import app.agents as pii_detector
sys.modules["pii_detector"] = pii_detector

from app.agents.document_cache import document_cache, DocumentCache
from app.agents.document_orchestrator import DocumentOrchestrator
from app.agents.document_classifier import DocumentClassifier
from app.agents.prompt_manager import PromptManager
from app.agents.intent_classifier import IntentClassifier
from app.agents.context_builder import ContextBuilder
from app.agents.response_formatter import ResponseFormatter
from app.agents.llm_router import LLMRouter
from app.agents.agents.privacy_rag_agent import PrivacyRAGAgent, demask_text


def test_required_orchestration_unit_tests():
    print("\n--- 1. Testing DocumentOrchestrator Unit Tests ---", flush=True)

    test_cases = [
        ("What is in the document?", "summary", "DOCUMENT_LEVEL", "FULL_DOCUMENT", True),
        ("Overview of this report", "summary", "DOCUMENT_LEVEL", "FULL_DOCUMENT", True),
        ("Summarize this document", "summary", "DOCUMENT_LEVEL", "FULL_DOCUMENT", True),
        ("Is this agreement compliance friendly?", "compliance", "DOCUMENT_LEVEL", "FULL_DOCUMENT", True),
        ("Analyse this invoice", "analysis", "DOCUMENT_LEVEL", "FULL_DOCUMENT", True),
        ("What is the PAN?", "question", "FACT_LEVEL", "SEMANTIC_RETRIEVAL", False),
        ("What is the GSTIN?", "question", "FACT_LEVEL", "SEMANTIC_RETRIEVAL", False),
    ]

    all_passed = True
    for query, intent, expected_scope, expected_strategy, expected_bypass in test_cases:
        plan = DocumentOrchestrator.orchestrate(query, intent=intent)
        print(f" Query: '{query}' ({intent}) -> Scope: {plan.query_scope} | Strategy: {plan.context_strategy} | Bypass: {plan.bypass_vector_search}", flush=True)

        if plan.query_scope == expected_scope and plan.context_strategy == expected_strategy and plan.bypass_vector_search == expected_bypass:
            print("   [PASS]", flush=True)
        else:
            print(f"   [FAIL] Expected ({expected_scope}, {expected_strategy}, {expected_bypass}), Got ({plan.query_scope}, {plan.context_strategy}, {plan.bypass_vector_search})", flush=True)
            all_passed = False

    return all_passed


def test_document_cache():
    print("\n--- 2. Testing DocumentCache Storage & Retrieval ---", flush=True)
    cache = DocumentCache()
    cache.store("doc_test_1", "Sample document masked text", {"<PAN_1>": "ABCDE1234F"}, file_name="invoice.pdf")

    assert cache.has_document("doc_test_1")
    assert cache.get_full_text("doc_test_1") == "Sample document masked text"
    assert cache.get_mapping("doc_test_1") == {"<PAN_1>": "ABCDE1234F"}
    print(" [PASS] DocumentCache stored and retrieved document structures cleanly.", flush=True)
    return True


def test_document_classifier():
    print("\n--- 3. Testing DocumentClassifier & Persona Assignment ---", flush=True)
    test_docs = [
        ("Master Service Agreement between Apex Corp and Cloud Vendor...", "Master Service Agreement", "Legal Contract Analyst"),
        ("Tax Invoice #INV-2026-001 Bill To: Apex Tech Subtotal: $5,000...", "Invoice", "Financial Auditor"),
        ("Patient Clinical Diagnostic Report Hospital: City Care Diagnosis: Acute Bronchitis...", "Medical Record", "Clinical Documentation Specialist"),
        ("Employee Onboarding Registration Form Department: Cloud Solutions Position: Senior Engineer...", "Employee Onboarding Form", "HR Specialist"),
        ("Abstract: We present a novel RAG architecture for privacy preservation in LLMs...", "Research Paper", "Research Analyst"),
    ]

    all_passed = True
    for text, expected_type, expected_persona in test_docs:
        res = DocumentClassifier.classify(text)
        if res.doc_type == expected_type and res.persona == expected_persona:
            print(f" [PASS] Detected '{res.doc_type}' -> Persona: '{res.persona}' (Conf: {res.confidence})", flush=True)
        else:
            print(f" [FAIL] Text: '{text[:40]}...' -> Expected ({expected_type}, {expected_persona}), Got ({res.doc_type}, {res.persona})", flush=True)
            all_passed = False

    return all_passed


def test_response_formatter():
    print("\n--- 4. Testing ResponseFormatter Disclaimer & Cliche Cleaning ---", flush=True)
    disclaimer_input = (
        "Based on available document excerpts, this document is designed to register a new employee.\n"
        "Furthermore, Additionally, Overall, the onboarding process is standard."
    )
    cleaned = ResponseFormatter.quality_review(disclaimer_input, "summary")
    assert "Based on available document excerpts" not in cleaned
    assert "This document is designed to" not in cleaned
    assert "Furthermore" not in cleaned
    print(" [PASS] ResponseFormatter cleaned disclaimers and overused AI cliches.", flush=True)
    return True


def test_end_to_end_active_document_qa():
    print("\n--- 5. Testing Active Document Protection ('What is in the document?') ---", flush=True)
    agent = PrivacyRAGAgent()

    masked_doc = {
        "masked_text": (
            "PURCHASE ORDER\n"
            "PO Number: <PO_1>\n"
            "Vendor: Acme Logistics Supply Corp\n"
            "Buyer: Apex Global Technologies Ltd.\n"
            "Item: High-Performance GPU Acceleration Clusters\n"
            "Quantity: 20 Units\n"
            "Total Value: $250,000.00\n"
            "Delivery Destination: Tech Park Facility, Bangalore"
        ),
        "mapping": {
            "<PO_1>": "PO-2026-9900"
        }
    }

    agent.ingest_masked_result(masked_doc, document_id="doc_po_7788", file_name="04_Supply_Chain_Purchase_Order.docx")

    # Generic document question
    generic_q = "What is in the document?"
    res = agent.answer_query(generic_q)

    print(f"\nQuery: '{generic_q}'", flush=True)
    print(f" -> Strategy Used: {res.get('context_strategy_used')}", flush=True)
    print(f" -> Bypassed Vector Search: {res.get('bypassed_vector_search')}", flush=True)
    print(f" -> Answer:\n{res.get('final_unmasked_answer')}", flush=True)

    answer_text = res.get("final_unmasked_answer", "")
    assert res.get("context_strategy_used") == "FULL_DOCUMENT"
    assert res.get("bypassed_vector_search") is True
    assert "no document context provided" not in answer_text.lower()
    assert "there is no document context" not in answer_text.lower()
    assert "PO-2026-9900" in answer_text or "Acme Logistics" in answer_text

    print("\n [PASS] Active Document Protection verified! 'What is in the document?' returned natural answer from cached document.", flush=True)
    return True


if __name__ == "__main__":
    print("==================================================", flush=True)
    print("  AI DOCUMENT ANALYST & ORCHESTRATOR TEST SUITE   ", flush=True)
    print("==================================================", flush=True)

    t1 = test_required_orchestration_unit_tests()
    t2 = test_document_cache()
    t3 = test_document_classifier()
    t4 = test_response_formatter()
    t5 = test_end_to_end_active_document_qa()

    print("\n==================================================", flush=True)
    if t1 and t2 and t3 and t4 and t5:
        print(" ALL ORCHESTRATION UNIT TESTS PASSED SUCCESSFULLY!", flush=True)
    else:
        print(" SOME UNIT TESTS FAILED.", flush=True)
    print("==================================================", flush=True)
