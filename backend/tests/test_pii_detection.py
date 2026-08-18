import sys
from pathlib import Path

# Add backend and agents directory to path
backend_dir = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == 'tests' else Path(__file__).resolve().parent
agents_dir = backend_dir / "app" / "agents"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(agents_dir) not in sys.path:
    sys.path.insert(0, str(agents_dir))

# Alias pii_detector module to app.agents
import app.agents as pii_detector
sys.modules["pii_detector"] = pii_detector

from app.agents.agents.pii_detection_agent import PIIDetectionAgent


def run_pii_detection_tests():
    print("==================================================")
    print("         PII DETECTION AGENT TEST SUITE          ")
    print("==================================================\n")

    agent = PIIDetectionAgent(enable_ocr=False, enable_llm_residual=False)

    test_cases = [
        {
            "name": "Financial Domain PII",
            "domain": "financial",
            "text": "Account holder Rajesh Kumar has PAN ABCDE1234F and Aadhaar 2345 6789 0123. Contact: rajesh.k@example.com or +919876543210."
        },
        {
            "name": "Medical / Healthcare PII",
            "domain": "medical",
            "text": "Patient Sarah Jenkins visited Apollo Hospital. Payment via Credit Card 4532 0151 2830 9182. Phone: 9812345678."
        },
        {
            "name": "General Corporate Data",
            "domain": "general",
            "text": "Send invoices to billing@acmecorp.com or call support line 9123456789."
        },
        {
            "name": "User Specimen Document",
            "domain": "general",
            "text": """Document Reference: DOC-13873
Primary Representative: Officer 4
Contact Email: contact.leaveandlicenseagreementmaharashtraformatspecimenpdf@tenant-domain.com | Direct Mobile: +91 917654321
Aadhaar Identification: 3461 3901 2345 | Taxpan ID: PIIK4432F"""
        }
    ]

    total_passed = 0

    for idx, tc in enumerate(test_cases, start=1):
        print(f"Test #{idx}: {tc['name']} [Domain: {tc['domain'].upper()}]")
        print(f"Input Text: \"{tc['text']}\"")
        
        res = agent.process_text_on_the_go(tc['text'], domain=tc['domain'])
        entities = res.get("detected_entities", [])
        
        print(f"Status: {res.get('status')}")
        print(f"Total Entities Detected: {res.get('total_count')}")
        print("Detected Entities:")
        for ent in entities:
            print(f"  - [{ent.get('label')}] '{ent.get('text')}' (Span: {ent.get('start')}-{ent.get('end')}) Confidence: {ent.get('score', 1.0)}")

        if res.get("status") == "success" and len(entities) > 0:
            print(">>> RESULT: PASSED [OK]\n")
            total_passed += 1
        else:
            print(">>> RESULT: FAILED [ERR]\n")

    print("==================================================")
    print(f"SUMMARY: {total_passed}/{len(test_cases)} Test Cases Passed Successfully.")
    print("==================================================")


if __name__ == "__main__":
    run_pii_detection_tests()
