import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == 'tests' else Path(__file__).resolve().parent
agents_dir = backend_dir / "app" / "agents"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(agents_dir) not in sys.path:
    sys.path.insert(0, str(agents_dir))

import app.agents as pii_detector
sys.modules["pii_detector"] = pii_detector

from app.agents.agents.pii_detection_agent import PIIDetectionAgent
from app.agents.agents.masking_agent import MaskingAgent

def run_check():
    agent = PIIDetectionAgent(enable_ocr=False)
    masker = MaskingAgent()

    sample_text = (
        "PURCHASE ORDER\n"
        "PO Number: PO-PS-2026-3391   |   Date: 18 July 2026\n"
        "Buyer: Privacy Shield Technologies Pvt. Ltd.\n"
        "GSTIN: 06AABCP9876K1Z3  |  Contact: procurement@privacyshield.example.com\n"
        "Vendor: Precision Components India Pvt. Ltd.\n"
        "Primary Contact: Mr. Rajesh Kumar Verma (Director – Sales)\n"
        "Email: rajesh.verma@precisioncomp.example.com\n"
        "Mobile: +91-98201-44556  |  Landline: +91-22-4567-8901\n"
        "PAN: AABCP4567M  |  GSTIN: 27AABCP4567M1Z8  |  MSME: UDYAM-MH-17-0012345\n"
        "Account Number: 012345678901  |  IFSC: ICIC0000123\n"
        "Warehouse Manager: Ms. Sunita Devi (warehouse@privacyshield.example.com)"
    )

    res = agent.process_text_on_the_go(sample_text, domain="supply_chain")
    print(f"Total Entities Detected: {res['total_count']}\n", flush=True)
    for e in res["detected_entities"]:
        print(f"  - [{e['label']}] '{e['text']}' (Span: {e['start']}-{e['end']})", flush=True)

    masked_res = masker.apply_hitl_masking(sample_text, res["detected_entities"])
    print("\n=================== MASKED TEXT ===================", flush=True)
    print(masked_res.masked_text, flush=True)
    print("===================================================", flush=True)

if __name__ == "__main__":
    run_check()
