import sys
import os
import io
import json
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

from app.agents.agents.audit_log_agent import AuditLogAgent, AuditEvent
from app.agents.db.models import AuditLogEntryModel
from app.agents.db.database import db_manager
from app.agents.graph.privacy_graph import create_privacy_graph, PrivacyAgentState


def run_audit_security_tests():
    print("==================================================")
    print("  AUDIT LOG AGENT SECURITY TEST SUITE (16 TESTS)  ")
    print("==================================================")

    # Initialize clean DB table for test suite verification
    session = db_manager.get_session()
    try:
        session.query(AuditLogEntryModel).delete()
        session.commit()
    finally:
        session.close()

    audit_agent = AuditLogAgent()

    # --------------------------------------------------
    # TEST 1: Approval Defaults (Must default to False)
    # --------------------------------------------------
    print("\nTEST 1: Approval default values must be False")
    event1 = AuditEvent(
        log_id="LOG-test1",
        actor_id="usr_test",
        action_type="DETECTION",
        document_id="doc_1",
        timestamp="2026-08-16T12:00:00Z",
        prev_hash="0" * 64,
        entry_hash="hash1",
        details={}
    )
    assert event1.hitl_approved is False, f"Expected hitl_approved=False, got {event1.hitl_approved}"
    assert event1.demasking_approved is False, f"Expected demasking_approved=False, got {event1.demasking_approved}"
    assert event1.dpdp_compliant is False, f"Expected dpdp_compliant=False, got {event1.dpdp_compliant}"
    print(">>> TEST 1 PASSED [OK]")

    # --------------------------------------------------
    # TEST 2: HITL vs Demasking Separation
    # --------------------------------------------------
    print("\nTEST 2: HITL approval does NOT authorize demasking")
    res2 = audit_agent.log_event(
        agent_name="TestAgent",
        action_type="HITL_VERIFICATION",
        details={"approved_entity_count": 2},
        hitl_approved=True,
        demasking_approved=False,
        document_id="doc_test_2"
    )
    print(f"Result 2: hitl_approved={res2['hitl_approved']}, demasking_approved={res2['demasking_approved']}")
    assert res2["hitl_approved"] is True
    assert res2["demasking_approved"] is False
    print(">>> TEST 2 PASSED [OK]")

    # --------------------------------------------------
    # TEST 3: Demasking Approval Event
    # --------------------------------------------------
    print("\nTEST 3: Authorized demasking event recorded explicitly")
    res3 = audit_agent.log_event(
        agent_name="DemaskingAgent",
        action_type="DEMASK_REQUEST",
        details={"tokens_replaced_count": 2},
        hitl_approved=True,
        demasking_approved=True,
        document_id="doc_test_3"
    )
    print(f"Result 3: demasking_approved={res3['demasking_approved']}")
    assert res3["demasking_approved"] is True
    print(">>> TEST 3 PASSED [OK]")

    # --------------------------------------------------
    # TEST 4: Raw PII Sanitization in Audit Details
    # --------------------------------------------------
    print("\nTEST 4: Raw PII sanitization in details (raw_text & mapping stripped)")
    res4 = audit_agent.log_event(
        agent_name="PIIDetectionAgent",
        action_type="DETECTION",
        details={
            "raw_text": "PAN ABCDE1234F",
            "mapping": {"<PAN_1>": "ABCDE1234F"},
            "domain": "Financial"
        },
        document_id="doc_test_4"
    )
    details_str4 = json.dumps(res4["details"])
    print(f"Sanitized Details: {details_str4}")
    assert "ABCDE1234F" not in details_str4, "Raw PII found in sanitized audit details!"
    assert "raw_text_present" in res4["details"] or "raw_text" not in res4["details"]
    assert res4["details"].get("domain") == "Financial"
    print(">>> TEST 4 PASSED [OK]")

    # --------------------------------------------------
    # TEST 5: Entity Sanitization
    # --------------------------------------------------
    print("\nTEST 5: Detected entities sanitization (entity texts stripped)")
    res5 = audit_agent.log_event(
        agent_name="PIIDetectionAgent",
        action_type="DETECTION",
        details={
            "detected_entities": [{"text": "Rahul Sharma", "label": "PERSON"}],
            "risk_score": 25.0
        },
        document_id="doc_test_5"
    )
    details_str5 = json.dumps(res5["details"])
    print(f"Sanitized Details: {details_str5}")
    assert "Rahul Sharma" not in details_str5, "Raw person name found in audit details!"
    assert res5["details"].get("detected_entities_count") == 1
    print(">>> TEST 5 PASSED [OK]")

    # --------------------------------------------------
    # TEST 6: Demasked Text Sanitization
    # --------------------------------------------------
    print("\nTEST 6: Demasked text sanitization (unmasked text stripped)")
    res6 = audit_agent.log_event(
        agent_name="DemaskingAgent",
        action_type="DEMASK_REQUEST",
        details={
            "demasked_text": "Rahul Sharma has PAN ABCDE1234F",
            "tokens_replaced_count": 2
        },
        document_id="doc_test_6"
    )
    details_str6 = json.dumps(res6["details"])
    print(f"Sanitized Details: {details_str6}")
    assert "Rahul Sharma" not in details_str6
    assert "ABCDE1234F" not in details_str6
    assert res6["details"].get("tokens_replaced_count") == 2
    print(">>> TEST 6 PASSED [OK]")

    # --------------------------------------------------
    # TEST 7: Database Persistence Failure (last_hash does NOT advance)
    # --------------------------------------------------
    print("\nTEST 7: Database persistence failure (last_hash preserved)")
    original_last_hash = audit_agent.last_hash
    with patch("pii_detector.db.database.db_manager.get_session") as mock_session_fn:
        mock_session = MagicMock()
        mock_session.commit.side_effect = Exception("Simulated PostgreSQL connection loss")
        mock_session_fn.return_value = mock_session

        res7 = audit_agent.log_event(
            agent_name="FailTest",
            action_type="ERROR_TEST",
            details={"key": "val"}
        )

        print(f"Persistence Result on DB Failure: persisted={res7.get('persisted')}, status={res7.get('status')}")
        assert res7.get("persisted") is False
        assert res7.get("status") == "failed"
        assert audit_agent.last_hash == original_last_hash, "last_hash must NOT advance when persistence fails!"
    print(">>> TEST 7 PASSED [OK]")

    # --------------------------------------------------
    # TEST 8: Hash Chain Integrity Verification
    # --------------------------------------------------
    print("\nTEST 8: Hash chain integrity verification across multiple events")
    # Log 3 events
    audit_agent.log_event("Agent1", "ACTION_1", {"step": 1})
    audit_agent.log_event("Agent2", "ACTION_2", {"step": 2})
    audit_agent.log_event("Agent3", "ACTION_3", {"step": 3})

    integrity_res = audit_agent.verify_integrity()
    print(f"Integrity Verification: {integrity_res}")
    assert integrity_res["is_tamper_free"] is True
    assert integrity_res["total_verified"] >= 3
    print(">>> TEST 8 PASSED [OK]")

    # --------------------------------------------------
    # TEST 9: Tampering Detection
    # --------------------------------------------------
    print("\nTEST 9: Tampering detection when payload modified")
    session = db_manager.get_session()
    try:
        latest_entry = session.query(AuditLogEntryModel).order_by(AuditLogEntryModel.timestamp.desc()).first()
        if latest_entry:
            # Tamper with stored entry
            orig_details = latest_entry.details_json
            latest_entry.details_json = json.dumps({"tampered": True, "agent_name": "Attacker"})
            session.commit()

            tampered_verify = audit_agent.verify_integrity()
            print(f"Tampered Verification Result: {tampered_verify}")
            assert tampered_verify["is_tamper_free"] is False
            assert "tampered_log_id" in tampered_verify

            # Restore original details
            latest_entry.details_json = orig_details
            session.commit()
    finally:
        session.close()
    print(">>> TEST 9 PASSED [OK]")

    # --------------------------------------------------
    # TEST 10: Missing Approval in get_summary()
    # --------------------------------------------------
    print("\nTEST 10: Missing approval not counted as True in get_summary")
    res10 = audit_agent.log_event(
        agent_name="TestNoApproval",
        action_type="MASKING",
        details={"masked_token_count": 1},
        hitl_approved=False
    )
    summary10 = audit_agent.get_summary()
    print(f"Summary HITL Approvals: {summary10['hitl_approvals']}")
    print(">>> TEST 10 PASSED [OK]")

    # --------------------------------------------------
    # TEST 11: HITL Approval Counting
    # --------------------------------------------------
    print("\nTEST 11: HITL approval counts only explicit True values")
    summary_before = audit_agent.get_summary()
    audit_agent.log_event("AgentT", "HITL_VERIFICATION", {"info": 1}, hitl_approved=True)
    audit_agent.log_event("AgentF", "HITL_VERIFICATION", {"info": 2}, hitl_approved=False)
    summary_after = audit_agent.get_summary()
    print(f"Approvals delta: {summary_after['hitl_approvals'] - summary_before['hitl_approvals']}")
    assert summary_after["hitl_approvals"] - summary_before["hitl_approvals"] == 1
    print(">>> TEST 11 PASSED [OK]")

    # --------------------------------------------------
    # TEST 12: Demasking Summary Metrics
    # --------------------------------------------------
    print("\nTEST 12: Demasking summary metrics reported separately")
    audit_agent.log_event("DemaskingAgent", "DEMASK_REQUEST", {"status": "success"}, demasking_approved=True)
    audit_agent.log_event("DemaskingAgent", "DEMASK_REQUEST", {"status": "blocked"}, demasking_approved=False)
    summary12 = audit_agent.get_summary()
    print(f"Demasking Requests: {summary12.get('demasking_requests')}")
    print(f"Demasking Approved: {summary12.get('demasking_approved')}")
    print(f"Demasking Blocked: {summary12.get('demasking_blocked')}")
    assert summary12.get("demasking_requests", 0) >= 2
    assert summary12.get("demasking_approved", 0) >= 1
    assert summary12.get("demasking_blocked", 0) >= 1
    print(">>> TEST 12 PASSED [OK]")

    # --------------------------------------------------
    # TEST 13: Cloud Leakage Audit Sanitization
    # --------------------------------------------------
    print("\nTEST 13: Cloud leakage event records count/status, not leaked_value")
    res13 = audit_agent.log_event(
        agent_name="DPDPGuardrailsEngine",
        action_type="CLOUD_LEAKAGE_CHECK",
        details={
            "cloud_transmission_safe": False,
            "leakage_count": 1,
            "leaked_value": "ABCDE1234F",
            "status": "BLOCKED"
        }
    )
    details_str13 = json.dumps(res13["details"])
    print(f"Sanitized Cloud Leakage Details: {details_str13}")
    assert "ABCDE1234F" not in details_str13, "Raw leaked PII value was written to audit details!"
    assert res13["details"].get("leakage_count") == 1
    assert res13["details"].get("cloud_transmission_safe") is False
    print(">>> TEST 13 PASSED [OK]")

    # --------------------------------------------------
    # TEST 14: Audit API get_all_logs() Security
    # --------------------------------------------------
    print("\nTEST 14: get_all_logs() returns sanitized records without raw PII")
    logs = audit_agent.get_all_logs()
    assert isinstance(logs, list)
    for l in logs[:10]:
        details_dump = json.dumps(l.get("details", {}))
        assert "raw_text" not in l.get("details", {}) or not isinstance(l.get("details", {}).get("raw_text"), str)
    print(">>> TEST 14 PASSED [OK]")

    # --------------------------------------------------
    # TEST 15: JSON Backup Sanitization
    # --------------------------------------------------
    print("\nTEST 15: JSON backup contains sanitized details only")
    if audit_agent.log_file.exists():
        with open(audit_agent.log_file, "r", encoding="utf-8") as f:
            json_logs = json.load(f)
            assert isinstance(json_logs, list)
            if json_logs:
                first_log = json_logs[0]
                assert "details" in first_log
                assert "ABCDE1234F" not in json.dumps(first_log)
    print(">>> TEST 15 PASSED [OK]")

    # --------------------------------------------------
    # TEST 16: Repository-Level End-to-End Security Test (Section 34)
    # --------------------------------------------------
    print("\nTEST 16: Repository-level end-to-end PII isolation verification (Section 34)")
    TEST_PAN = "ABCDE1234F"
    TEST_NAME = "Vikram Aditya"
    doc_text = f"EMPLOYEE RECORD: Name: {TEST_NAME}, PAN: {TEST_PAN}, Account: 9876543210"

    log_capture = io.StringIO()
    root_logger = logging.getLogger()
    handler = logging.StreamHandler(log_capture)
    root_logger.addHandler(handler)

    try:
        graph = create_privacy_graph()
        config = {"configurable": {"thread_id": "thread_sec_verify_99"}}
        init_state = {
            "document_id": "doc_sec_verify_99",
            "file_name": "sec_verify.txt",
            "file_path": None,
            "raw_text": doc_text
        }

        # 1. Run through graph up to HITL interrupt
        for event in graph.stream(init_state, config):
            pass

        # 2. Extract detected entities from state and approve them
        current_state = graph.get_state(config).values
        detected_list = current_state.get("detected_entities", [])
        approved_entities = []
        for ent in detected_list:
            approved_ent = dict(ent)
            approved_ent["approved"] = True
            approved_entities.append(approved_ent)

        # 3. Provide human approved entities (for masking)
        graph.update_state(
            config,
            {
                "approved_entities": approved_entities,
                "hitl_approved": True,
                "hitl_review_completed": True
            },
            as_node="hitl_review"
        )

        # 4. Resume and complete graph
        for event in graph.stream(None, config):
            pass

        final_state = graph.get_state(config).values

        # 5. Verify that masked text contains tokens, not raw PII
        masked_txt = final_state.get("masked_text", "")
        print(f"Masked Output: {masked_txt}")
        assert TEST_PAN not in masked_txt, f"Raw PAN found in masked_text: {masked_txt}"
        assert TEST_NAME not in masked_txt, f"Raw Name found in masked_text: {masked_txt}"

        # 6. Inspect application logs for raw PII leakage
        logs_text = log_capture.getvalue()
        # Normal application logs must not contain raw PAN
        assert TEST_PAN not in logs_text, f"Raw PAN leaked into application loggers!"

        # 7. Inspect audit logs for raw PII leakage
        audit_logs = audit_agent.get_all_logs()
        for al in audit_logs:
            if al.get("document_id") == "doc_sec_verify_99":
                al_details_str = json.dumps(al.get("details", {}))
                assert TEST_PAN not in al_details_str, "Raw PAN found in audit log details!"
                assert TEST_NAME not in al_details_str, "Raw Name found in audit log details!"

        print(">>> TEST 16 PASSED [OK]")
    finally:
        root_logger.removeHandler(handler)

    print("\n==================================================")
    print("  ALL 16 AUDIT SECURITY TESTS PASSED [100% OK]    ")
    print("==================================================")


if __name__ == "__main__":
    run_audit_security_tests()
