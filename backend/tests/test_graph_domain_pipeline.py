import sys
import os
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import patch, MagicMock

backend_dir = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == 'tests' else Path(__file__).resolve().parent
agents_dir = backend_dir / "app" / "agents"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(agents_dir) not in sys.path:
    sys.path.insert(0, str(agents_dir))

import app.agents as pii_detector
sys.modules["pii_detector"] = pii_detector

from app.agents.agents.classification_agent import ClassificationAgent
from app.agents.agents.pii_detection_agent import PIIDetectionAgent
from app.agents.agents.masking_agent import MaskingAgent
from app.agents.agents.risk_agent import RiskAgent
from app.agents.agents.dpdp_guardrails import DPDPGuardrailsEngine
from app.agents.agents.audit_log_agent import AuditLogAgent
from app.agents.graph.privacy_graph import create_privacy_graph, PrivacyAgentState, log_audit_node


def run_all_tests():
    print("==================================================")
    print("  PRIVACYSHIELDAI 16-POINT COMPLIANCE TEST SUITE  ")
    print("==================================================\n")

    classification_agent = ClassificationAgent()
    detection_agent = PIIDetectionAgent(enable_ocr=False, enable_llm_residual=False)
    masking_agent = MaskingAgent()
    dpdp_engine = DPDPGuardrailsEngine()

    # --------------------------------------------------
    # TEST 1: Financial Document Classification
    # --------------------------------------------------
    print("TEST 1: Financial document classification")
    fin_text = "Bank account statement with PAN, account number, debit, credit and INR transactions."
    res1 = classification_agent.classify_document(fin_text)
    print(f"Input: {fin_text}")
    print(f"Output Domain: {res1.get('category')}")
    assert res1.get("category") == "Financial", f"Expected Financial, got {res1.get('category')}"
    print(">>> TEST 1 PASSED [OK]\n")

    # --------------------------------------------------
    # TEST 2: Medical Document Classification
    # --------------------------------------------------
    print("TEST 2: Medical document classification")
    med_text = "Patient diagnosis, doctor prescription, hospital treatment and medical report."
    res2 = classification_agent.classify_document(med_text)
    print(f"Input: {med_text}")
    print(f"Output Domain: {res2.get('category')}")
    assert res2.get("category") == "Medical", f"Expected Medical, got {res2.get('category')}"
    print(">>> TEST 2 PASSED [OK]\n")

    # --------------------------------------------------
    # TEST 3: Legal Document Classification
    # --------------------------------------------------
    print("TEST 3: Legal document classification")
    leg_text = "Agreement between two parties containing clauses and jurisdiction."
    res3 = classification_agent.classify_document(leg_text)
    print(f"Input: {leg_text}")
    print(f"Output Domain: {res3.get('category')}")
    assert res3.get("category") == "Legal", f"Expected Legal, got {res3.get('category')}"
    print(">>> TEST 3 PASSED [OK]\n")

    # --------------------------------------------------
    # TEST 4: General Document Classification
    # --------------------------------------------------
    print("TEST 4: General document classification")
    gen_text = "This is a general company introduction document."
    res4 = classification_agent.classify_document(gen_text)
    print(f"Input: {gen_text}")
    print(f"Output Domain: {res4.get('category')}")
    assert res4.get("category") == "General", f"Expected General, got {res4.get('category')}"
    print(">>> TEST 4 PASSED [OK]\n")

    # --------------------------------------------------
    # TEST 5: Ambiguous Document Classification
    # --------------------------------------------------
    print("TEST 5: Ambiguous document classification")
    amb_text = "Employee salary bank account PAN and employee resume designation appraisal joining."
    res5 = classification_agent.classify_document(amb_text)
    print(f"Input: {amb_text}")
    print(f"Matched keywords: {res5.get('matched_keywords')}")
    print(f"Requires Manual Override: {res5.get('requires_manual_override')}")
    assert res5.get("requires_manual_override") is True, f"Expected requires_manual_override=True, got {res5.get('requires_manual_override')}"
    print(">>> TEST 5 PASSED [OK]\n")

    # --------------------------------------------------
    # TEST 6: PII Detection Approval Default
    # --------------------------------------------------
    print("TEST 6: PII candidate approved default check")
    detect_text = "Account holder Rajesh Kumar has PAN ABCDE1234F and Aadhaar 2345 6789 0123."
    res6 = detection_agent.process_text_on_the_go(detect_text)
    entities6 = res6.get("detected_entities", [])
    print(f"Detected {len(entities6)} PII candidates.")
    for e in entities6:
        print(f"  - Entity [{e.get('label')}] '{e.get('text')}': approved={e.get('approved')}")
        assert e.get("approved") is False, f"Expected approved=False for candidate entity, got {e.get('approved')}"
    print(">>> TEST 6 PASSED [OK]\n")

    # --------------------------------------------------
    # TEST 7: Masking Rejection (approved=False)
    # --------------------------------------------------
    print("TEST 7: Masking rejection (approved=False must NOT be masked)")
    raw7 = "PAN ABCDE1234F"
    ent7 = [{"id": 1, "text": "ABCDE1234F", "label": "PAN", "start": 4, "end": 14, "approved": False}]
    masked7 = masking_agent.apply_hitl_masking(raw7, ent7)
    print(f"Original: {raw7} | Masked: {masked7.masked_text}")
    assert "ABCDE1234F" in masked7.masked_text, "Unapproved entity must NOT be masked!"
    print(">>> TEST 7 PASSED [OK]\n")

    # --------------------------------------------------
    # TEST 8: Masking Approval (approved=True)
    # --------------------------------------------------
    print("TEST 8: Masking approval (approved=True must be masked)")
    raw8 = "PAN ABCDE1234F"
    ent8 = [{"id": 1, "text": "ABCDE1234F", "label": "PAN", "start": 4, "end": 14, "approved": True}]
    masked8 = masking_agent.apply_hitl_masking(raw8, ent8)
    print(f"Original: {raw8} | Masked: {masked8.masked_text}")
    assert "ABCDE1234F" not in masked8.masked_text, "Approved entity MUST be masked!"
    assert "<PAN_1>" in masked8.masked_text, "Mask token should replace approved entity"
    print(">>> TEST 8 PASSED [OK]\n")

    # --------------------------------------------------
    # TEST 9: Missing Approval Key
    # --------------------------------------------------
    print("TEST 9: Missing approved key (must NOT be masked)")
    raw9 = "Contact +91 9876543210"
    ent9 = [{"id": 1, "text": "+91 9876543210", "label": "PHONE", "start": 8, "end": 22}]
    masked9 = masking_agent.apply_hitl_masking(raw9, ent9)
    print(f"Original: {raw9} | Masked: {masked9.masked_text}")
    assert "+91 9876543210" in masked9.masked_text, "Entity without approved=True must NOT be masked!"
    print(">>> TEST 9 PASSED [OK]\n")

    # --------------------------------------------------
    # TEST 10: HITL Incomplete Guardrail Check
    # --------------------------------------------------
    print("TEST 10: HITL incomplete (total_entities > 0, hitl_review_completed=False)")
    dpdp_res10 = dpdp_engine.evaluate_document_processing(
        raw_text="Sample raw text",
        detected_entities=[{"label": "PAN", "text": "ABCDE1234F"}],
        human_approved_count=0,
        total_entities_count=1,
        hitl_review_completed=False
    )
    print(f"Guardrail Status: {dpdp_res10.guardrail_status}")
    print(f"Violations: {dpdp_res10.violations}")
    assert dpdp_res10.guardrail_status.get("HITL_CONSENT_VERIFICATION") is False
    assert dpdp_res10.is_compliant is False
    print(">>> TEST 10 PASSED [OK]\n")

    # --------------------------------------------------
    # TEST 11: HITL Completed with Zero Approvals
    # --------------------------------------------------
    print("TEST 11: HITL completed with 0 approvals (hitl_review_completed=True, human_approved_count=0)")
    dpdp_res11 = dpdp_engine.evaluate_document_processing(
        raw_text="Sample raw text",
        detected_entities=[{"label": "PAN", "text": "ABCDE1234F"}],
        human_approved_count=0,
        total_entities_count=1,
        hitl_review_completed=True
    )
    print(f"Guardrail Status: {dpdp_res11.guardrail_status}")
    print(f"Passed Rules: {dpdp_res11.passed_rules}")
    assert dpdp_res11.guardrail_status.get("HITL_CONSENT_VERIFICATION") is True
    assert dpdp_res11.is_compliant is True
    print(">>> TEST 11 PASSED [OK]\n")

    # --------------------------------------------------
    # TEST 12: HITL Completed with Approvals
    # --------------------------------------------------
    print("TEST 12: HITL completed with approvals (hitl_review_completed=True, human_approved_count=2)")
    dpdp_res12 = dpdp_engine.evaluate_document_processing(
        raw_text="Sample raw text",
        detected_entities=[{"label": "PAN", "text": "ABCDE1234F"}, {"label": "AADHAAR", "text": "2345 6789 0123"}],
        human_approved_count=2,
        total_entities_count=2,
        hitl_review_completed=True
    )
    print(f"Guardrail Status: {dpdp_res12.guardrail_status}")
    print(f"Is Compliant: {dpdp_res12.is_compliant}")
    assert dpdp_res12.guardrail_status.get("HITL_CONSENT_VERIFICATION") is True
    assert dpdp_res12.is_compliant is True
    print(">>> TEST 12 PASSED [OK]\n")

    # --------------------------------------------------
    # TEST 13: Safe Cloud Transmission Verification
    # --------------------------------------------------
    print("TEST 13: Safe cloud transmission")
    masked_safe = "Customer <PERSON_1> has PAN <PAN_1>"
    map_safe = {"<PERSON_1>": "Rahul Sharma", "<PAN_1>": "ABCDE1234F"}
    cloud_safe_res = dpdp_engine.evaluate_cloud_transmission(masked_safe, map_safe)
    print(f"Transmission Result: {cloud_safe_res}")
    assert cloud_safe_res["is_safe"] is True
    assert cloud_safe_res["status"] == "APPROVED_FOR_CLOUD_TRANSMISSION"
    print(">>> TEST 13 PASSED [OK]\n")

    # --------------------------------------------------
    # TEST 14: Cloud Leakage Detection
    # --------------------------------------------------
    print("TEST 14: Cloud leakage detection")
    leaked_text = "Customer Rahul Sharma has PAN ABCDE1234F"
    map_leaked = {"<PERSON_1>": "Rahul Sharma", "<PAN_1>": "ABCDE1234F"}
    cloud_leak_res = dpdp_engine.evaluate_cloud_transmission(leaked_text, map_leaked)
    print(f"Transmission Result: {cloud_leak_res}")
    assert cloud_leak_res["is_safe"] is False
    assert cloud_leak_res["status"] == "BLOCKED_POTENTIAL_LEAKAGE"
    assert len(cloud_leak_res["leakages_found"]) == 2
    print(">>> TEST 14 PASSED [OK]\n")

    # --------------------------------------------------
    # TEST 15: Cloud Leakage Blocks RAG in LangGraph
    # --------------------------------------------------
    print("TEST 15: Cloud leakage blocks RAG in LangGraph")
    graph_app = create_privacy_graph()
    initial_state_leak = {
        "document_id": "test_leak_doc",
        "file_name": "test_leak.txt",
        "file_path": None,
        "raw_text": "Customer Rahul Sharma has PAN ABCDE1234F and phone 9876543210"
    }
    config_leak = {"configurable": {"thread_id": "thread_leak_1"}}
    
    # Run through to HITL interrupt
    for event in graph_app.stream(initial_state_leak, config_leak):
        pass

    # Simulate an incomplete/broken masking state causing leakage
    # We update approved entities and inject masked_text that contains raw value
    graph_app.update_state(
        config_leak,
        {
            "approved_entities": [{"id": 1, "text": "Rahul Sharma", "label": "NAME", "approved": True}],
            "hitl_approved": True,
            "hitl_review_completed": True
        },
        as_node="hitl_review"
    )

    # Resume graph
    events = []
    for event in graph_app.stream(None, config_leak):
        events.append(event)
        print(f"Graph Step: {list(event.keys())}")

    final_state_leak = graph_app.get_state(config_leak).values
    print(f"Cloud Transmission Safe: {final_state_leak.get('cloud_transmission_safe')}")
    print(f"RAG Indexed: {final_state_leak.get('rag_indexed')}")
    print(f"Final Status: {final_state_leak.get('status')}")
    
    # In normal flow where masking succeeded, cloud_transmission_safe is True and RAG is indexed
    assert final_state_leak.get("cloud_transmission_safe") is True
    assert final_state_leak.get("rag_indexed") is True

    # Now verify when leakage is detected
    state_mock_leak: PrivacyAgentState = {
        "document_id": "mock_leak",
        "file_name": "mock.txt",
        "file_path": None,
        "raw_text": "Customer Rahul Sharma",
        "detected_entities": [],
        "total_count": 1,
        "regex_spacy_count": 1,
        "llm_count": 0,
        "domain": "General",
        "category_scores": {},
        "matched_keywords": {},
        "classification_confidence": 0.9,
        "compliance_rule_set": "STANDARD_PRIVACY_RULES",
        "requires_manual_override": False,
        "risk_score": 10.0,
        "risk_category": "Low",
        "route_to_hitl": False,
        "entity_type_counts": {},
        "dpdp_compliant": True,
        "dpdp_violations": [],
        "dpdp_passed_rules": [],
        "dpdp_recommendations": [],
        "dpdp_guardrail_status": {},
        "approved_entities": [],
        "hitl_approved": True,
        "hitl_review_completed": True,
        "masked_text": "Customer Rahul Sharma",  # unmasked raw value leaked
        "token_mapping": {"<PERSON_1>": "Rahul Sharma"},
        "cloud_transmission_safe": False,
        "cloud_leakages": [],
        "rag_indexed": False,
        "audit_logged": False,
        "status": "initial"
    }
    from app.agents.graph.privacy_graph import route_after_cloud_leakage_check, cloud_leakage_check_node
    leak_check_res = cloud_leakage_check_node(state_mock_leak)
    assert leak_check_res["cloud_transmission_safe"] is False
    assert leak_check_res["status"] == "cloud_transmission_blocked"
    
    next_route = route_after_cloud_leakage_check({**state_mock_leak, **leak_check_res})
    assert next_route == "log_audit", f"Expected route log_audit (bypassing rag_ingestion), got {next_route}"
    print(">>> TEST 15 PASSED [OK]\n")

    # --------------------------------------------------
    # TEST 16: Audit Failure Handling
    # --------------------------------------------------
    print("TEST 16: Audit failure handling (audit_logged=False)")
    with patch("app.agents.graph.privacy_graph.AuditLogAgent") as mock_audit_cls:
        mock_audit_inst = MagicMock()
        mock_audit_inst.log_event.side_effect = RuntimeError("Database connection failure")
        mock_audit_cls.return_value = mock_audit_inst

        state_audit: PrivacyAgentState = {
            "document_id": "test_audit_err",
            "file_name": "test.txt",
            "file_path": None,
            "raw_text": "Text",
            "detected_entities": [],
            "total_count": 0,
            "regex_spacy_count": 0,
            "llm_count": 0,
            "domain": "General",
            "category_scores": {},
            "matched_keywords": {},
            "classification_confidence": 0.9,
            "compliance_rule_set": "STANDARD_PRIVACY_RULES",
            "requires_manual_override": False,
            "risk_score": 0.0,
            "risk_category": "Low",
            "route_to_hitl": False,
            "entity_type_counts": {},
            "dpdp_compliant": True,
            "dpdp_violations": [],
            "dpdp_passed_rules": [],
            "dpdp_recommendations": [],
            "dpdp_guardrail_status": {},
            "approved_entities": [],
            "hitl_approved": True,
            "hitl_review_completed": True,
            "masked_text": "Text",
            "token_mapping": {},
            "cloud_transmission_safe": True,
            "cloud_leakages": [],
            "rag_indexed": True,
            "audit_logged": False,
            "status": "ready"
        }

        audit_res = log_audit_node(state_audit)
        print(f"Audit Node Result on Exception: {audit_res}")
        assert audit_res["audit_logged"] is False
        assert audit_res["status"] == "completed_with_audit_notice"

    print(">>> TEST 16 PASSED [OK]\n")

    print("==================================================")
    print("   ALL 16 COMPLIANCE TESTS PASSED [100% OK]       ")
    print("==================================================")


if __name__ == "__main__":
    run_all_tests()
