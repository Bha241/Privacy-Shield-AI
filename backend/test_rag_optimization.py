import sys
import os
from pathlib import Path

# Add backend and agents directory to path
backend_dir = Path(__file__).resolve().parent
agents_dir = backend_dir / "app" / "agents"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(agents_dir) not in sys.path:
    sys.path.insert(0, str(agents_dir))

# Alias pii_detector module to app.agents
import app.agents as pii_detector
sys.modules["pii_detector"] = pii_detector

from app.agents.agents.privacy_rag_agent import PrivacyRAGAgent, demask_text


def test_rag_pipeline():
    print("==================================================")
    print("          PRIVACY RAG OPTIMIZATION TEST SUITE    ")
    print("==================================================\n")

    agent = PrivacyRAGAgent()

    # 1. Document Ingestion Test
    masked_doc = {
        "masked_text": (
            "PATIENT CLINICAL REPORT\n"
            "Patient Name: <NAME_1>\n"
            "Aadhaar Number: <AADHAAR_1>\n"
            "Date of Visit: 2026-08-01\n"
            "Attending Physician: Dr. Robert Vance\n"
            "Hospital: City Care Super Specialty Hospital\n\n"
            "Clinical Notes:\n"
            "Patient <NAME_1> presented with complaints of persistent dry cough, fatigue, and mild fever (100.4 F) for 4 days. "
            "Chest X-Ray reveals mild pulmonary congestion. Lab reports indicate elevated CRP levels (18 mg/L).\n\n"
            "Diagnosis & Plan:\n"
            "Primary Diagnosis: Acute Bronchitis with secondary inflammation.\n"
            "Treatment Plan:\n"
            "1. Tab Azithromycin 500mg once daily for 5 days.\n"
            "2. Syrup CoughRelief 10ml thrice daily.\n"
            "3. Adequate rest and steam inhalation.\n\n"
            "Follow Up: Review in clinic after 7 days or immediately if dyspnea worsens."
        ),
        "mapping": {
            "<NAME_1>": "Sunita Verma",
            "<AADHAAR_1>": "9876 5432 1098"
        }
    }

    print("Step 1: Ingesting Sanitized Document...")
    success = agent.ingest_masked_result(masked_doc, document_id="doc_test_101")
    print(f"Ingestion Status: {success}\n")

    # 2. Test Queries
    queries = [
        "What is the patient's primary diagnosis and treatment plan?",
        "Who is the attending physician and what hospital was visited?",
        "Summarize the patient report."
    ]

    for idx, q in enumerate(queries, start=1):
        print(f"--- Test Query #{idx}: '{q}' ---")
        res = agent.answer_query(q, document_id="doc_test_101")

        print(f"Model Engine Used: {res.get('model_used')}")
        print(f"Sources Retrieved: {res.get('sources_retrieved')}")
        print("\n[Sanitized Response Sent to User/LLM]:")
        print(res.get("masked_response"))
        print("\n[Final De-masked Output]:")
        print(res.get("final_unmasked_answer"))
        print("--------------------------------------------------\n")

    # 3. Test Demasking Robustness
    print("Step 3: Testing Fuzzy Token Demasking...")
    test_cases = [
        ("Patient <NAME_1> has Aadhaar <AADHAAR_1>.", "Patient Sunita Verma has Aadhaar 9876 5432 1098."),
        ("Diagnosis for <NAME 1> confirmed.", "Diagnosis for Sunita Verma confirmed."),
        ("Contact NAME_1 for follow-up.", "Contact Sunita Verma for follow-up.")
    ]

    mapping = {"<NAME_1>": "Sunita Verma", "<AADHAAR_1>": "9876 5432 1098"}
    all_fuzzy_passed = True
    for text_in, expected_out in test_cases:
        actual_out = demask_text(text_in, mapping)
        if actual_out == expected_out:
            print(f" [PASS] '{text_in}' -> '{actual_out}'")
        else:
            print(f" [FAIL] '{text_in}' -> Expected: '{expected_out}', Got: '{actual_out}'")
            all_fuzzy_passed = False

    print("\n==================================================")
    if all_fuzzy_passed:
        print("ALL RAG OPTIMIZATION TESTS PASSED SUCCESSFULLY!")
    else:
        print("SOME DEMASKING TESTS FAILED!")
    print("==================================================")


if __name__ == "__main__":
    test_rag_pipeline()
