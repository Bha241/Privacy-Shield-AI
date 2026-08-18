import sys
import os
import io
import logging
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

from app.agents.agents.demasking_agent import DemaskingAgent
from app.agents.agents.audit_log_agent import AuditLogAgent
from app.agents.graph.privacy_graph import PrivacyAgentState


def run_demasking_security_tests():
    print("==================================================")
    print("  DEMASKING AGENT SECURITY TEST SUITE (10 TESTS)  ")
    print("==================================================")

    demask_agent = DemaskingAgent()

    # --------------------------------------------------
    # TEST 1: Default behavior (No authorization -> BLOCKED)
    # --------------------------------------------------
    print("\nTEST 1: Default behavior without authorization")
    masked_text1 = "Customer <NAME_1> with PAN <PAN_1>."
    mapping1 = {"<NAME_1>": "Rahul Sharma", "<PAN_1>": "ABCDE1234F"}
    
    # Call without passing user_approved
    res1 = demask_agent.demask_text(masked_text1, mapping1)
    print(f"Result: {res1}")
    assert res1["status"] == "blocked", f"Expected blocked, got {res1['status']}"
    assert res1["is_demasked"] is False, "Expected is_demasked == False"
    assert res1["output_text"] == masked_text1, "Masked text must remain unmodified"
    assert "Rahul Sharma" not in res1["output_text"], "Raw PII must never be returned when blocked"
    assert "ABCDE1234F" not in res1["output_text"], "Raw PII must never be returned when blocked"
    print(">>> TEST 1 PASSED [OK]")

    # --------------------------------------------------
    # TEST 2: Explicit False (user_approved=False -> BLOCKED)
    # --------------------------------------------------
    print("\nTEST 2: Explicit user_approved=False")
    res2 = demask_agent.demask_text(masked_text1, mapping1, user_approved=False)
    print(f"Result: {res2}")
    assert res2["status"] == "blocked"
    assert res2["is_demasked"] is False
    assert res2["output_text"] == masked_text1
    print(">>> TEST 2 PASSED [OK]")

    # --------------------------------------------------
    # TEST 3: Explicit True (user_approved=True -> SUCCESS)
    # --------------------------------------------------
    print("\nTEST 3: Explicit user_approved=True")
    res3 = demask_agent.demask_text(masked_text1, mapping1, user_approved=True)
    print(f"Result: {res3}")
    assert res3["status"] == "success"
    assert res3["is_demasked"] is True
    assert res3["output_text"] == "Customer Rahul Sharma with PAN ABCDE1234F."
    assert set(res3["tokens_replaced"]) == {"<NAME_1>", "<PAN_1>"}
    assert res3["replaced_count"] == 2
    print(">>> TEST 3 PASSED [OK]")

    # --------------------------------------------------
    # TEST 4: Empty Text
    # --------------------------------------------------
    print("\nTEST 4: Empty text input")
    res4 = demask_agent.demask_text("", mapping1, user_approved=True)
    print(f"Result: {res4}")
    assert res4["status"] == "success"
    assert res4["is_demasked"] is False
    assert res4["output_text"] == ""
    assert res4["replaced_count"] == 0
    print(">>> TEST 4 PASSED [OK]")

    # --------------------------------------------------
    # TEST 5: Empty Mapping
    # --------------------------------------------------
    print("\nTEST 5: Empty mapping")
    res5 = demask_agent.demask_text(masked_text1, {}, user_approved=True)
    print(f"Result: {res5}")
    assert res5["status"] == "success"
    assert res5["is_demasked"] is False
    assert res5["output_text"] == masked_text1
    assert res5["replaced_count"] == 0
    print(">>> TEST 5 PASSED [OK]")

    # --------------------------------------------------
    # TEST 6: Missing Tokens in Mapping
    # --------------------------------------------------
    print("\nTEST 6: Missing tokens (mapping has tokens not in text)")
    mapping6 = {
        "<NAME_1>": "Rahul Sharma",
        "<PAN_1>": "ABCDE1234F",
        "<PHONE_1>": "9876543210",
        "<EMAIL_1>": "rahul@example.com"
    }
    # Only <NAME_1> and <PAN_1> are in masked_text1
    res6 = demask_agent.demask_text(masked_text1, mapping6, user_approved=True)
    print(f"Result: {res6}")
    assert res6["status"] == "success"
    assert set(res6["tokens_replaced"]) == {"<NAME_1>", "<PAN_1>"}
    assert "<PHONE_1>" not in res6["tokens_replaced"]
    assert "<EMAIL_1>" not in res6["tokens_replaced"]
    assert res6["replaced_count"] == 2
    print(">>> TEST 6 PASSED [OK]")

    # --------------------------------------------------
    # TEST 7: Masking Approval Must NOT Authorize Demasking
    # --------------------------------------------------
    print("\nTEST 7: Masking approval (hitl_approved=True) must NOT authorize demasking")
    state7: PrivacyAgentState = {
        "document_id": "doc_7",
        "file_name": "doc.txt",
        "file_path": None,
        "raw_text": "Customer Rahul Sharma",
        "detected_entities": [{"id": 1, "text": "Rahul Sharma", "label": "NAME", "approved": True}],
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
        "approved_entities": [{"id": 1, "text": "Rahul Sharma", "label": "NAME", "approved": True}],
        "hitl_approved": True,  # MASKING APPROVED
        "hitl_review_completed": True,
        "masked_text": "Customer <NAME_1>",
        "token_mapping": {"<NAME_1>": "Rahul Sharma"},
        "cloud_transmission_safe": True,
        "cloud_leakages": [],
        "demasking_requested": False,
        "demasking_approved": False,  # DEMASKING NOT APPROVED
        "demasking_status": "none",
        "demasked_text": None,
        "rag_indexed": True,
        "audit_logged": True,
        "status": "completed"
    }

    # Verify demasking is blocked when demasking_approved is False even if hitl_approved is True
    is_demask_authorized = state7.get("demasking_approved", False) is True
    res7 = demask_agent.demask_text(
        state7["masked_text"],
        state7["token_mapping"],
        user_approved=is_demask_authorized
    )
    print(f"Demask Authorized: {is_demask_authorized}")
    print(f"Result: {res7}")
    assert is_demask_authorized is False
    assert res7["status"] == "blocked"
    assert res7["is_demasked"] is False
    assert res7["output_text"] == "Customer <NAME_1>"
    print(">>> TEST 7 PASSED [OK]")

    # --------------------------------------------------
    # TEST 8: Explicit Demasking Authorization
    # --------------------------------------------------
    print("\nTEST 8: Explicit demasking authorization (demasking_approved=True)")
    state8 = dict(state7)
    state8["demasking_requested"] = True
    state8["demasking_approved"] = True  # EXPLICIT SERVER/TRUSTED AUTHORIZATION

    is_demask_authorized8 = state8.get("demasking_approved", False) is True
    res8 = demask_agent.demask_text(
        state8["masked_text"],
        state8["token_mapping"],
        user_approved=is_demask_authorized8
    )
    print(f"Demask Authorized: {is_demask_authorized8}")
    print(f"Result: {res8}")
    assert is_demask_authorized8 is True
    assert res8["status"] == "success"
    assert res8["is_demasked"] is True
    assert res8["output_text"] == "Customer Rahul Sharma"
    print(">>> TEST 8 PASSED [OK]")

    # --------------------------------------------------
    # TEST 9: Audit Demasking Actions (Without Raw PII)
    # --------------------------------------------------
    print("\nTEST 9: Audit demasking events (zero raw PII in audit log)")
    mock_audit = MagicMock()

    # 9a: Blocked demasking audit
    demask_agent.demask_text(
        masked_text1,
        mapping1,
        user_approved=False,
        audit_agent=mock_audit,
        document_id="doc_audit_test",
        actor_id="usr_tester"
    )
    assert mock_audit.log_event.called
    blocked_call_args = mock_audit.log_event.call_args[1]
    print(f"Blocked Audit Call Details: {blocked_call_args['details']}")
    assert blocked_call_args["action_type"] == "DEMASK_REQUEST"
    assert blocked_call_args["user_approved"] is False
    assert blocked_call_args["details"]["status"] == "blocked"
    # Ensure no raw PII in details
    assert "Rahul Sharma" not in str(blocked_call_args["details"])
    assert "ABCDE1234F" not in str(blocked_call_args["details"])

    # 9b: Successful demasking audit
    mock_audit.reset_mock()
    demask_agent.demask_text(
        masked_text1,
        mapping1,
        user_approved=True,
        audit_agent=mock_audit,
        document_id="doc_audit_test",
        actor_id="usr_tester"
    )
    assert mock_audit.log_event.called
    success_call_args = mock_audit.log_event.call_args[1]
    print(f"Success Audit Call Details: {success_call_args['details']}")
    assert success_call_args["action_type"] == "DEMASK_REQUEST"
    assert success_call_args["user_approved"] is True
    assert success_call_args["details"]["status"] == "success"
    assert success_call_args["details"]["tokens_replaced_count"] == 2
    # Ensure no raw PII in details
    assert "Rahul Sharma" not in str(success_call_args["details"])
    assert "ABCDE1234F" not in str(success_call_args["details"])
    print(">>> TEST 9 PASSED [OK]")

    # --------------------------------------------------
    # TEST 10: Logging Security (No raw PII in log records)
    # --------------------------------------------------
    print("\nTEST 10: Logging security (zero raw PII in application loggers)")
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    test_logger = logging.getLogger("app.agents.agents.demasking_agent")
    test_logger.setLevel(logging.DEBUG)
    test_logger.addHandler(handler)

    try:
        # Run blocked, successful, and error demasking
        demask_agent.demask_text(masked_text1, mapping1, user_approved=False)
        demask_agent.demask_text(masked_text1, mapping1, user_approved=True)
        # Test error handling
        with patch.object(demask_agent.masker, "unmask", side_effect=Exception("Simulated masker failure")):
            demask_agent.demask_text(masked_text1, mapping1, user_approved=True)

        log_contents = log_capture.getvalue()
        print("Captured Logs:")
        print(log_contents)

        assert "Rahul Sharma" not in log_contents, "Raw PII found in logs!"
        assert "ABCDE1234F" not in log_contents, "Raw PII found in logs!"
        print(">>> TEST 10 PASSED [OK]")
    finally:
        test_logger.removeHandler(handler)

    print("\n==================================================")
    print("  ALL 10 DEMASKING SECURITY TESTS PASSED [100% OK]  ")
    print("==================================================")


if __name__ == "__main__":
    run_demasking_security_tests()
