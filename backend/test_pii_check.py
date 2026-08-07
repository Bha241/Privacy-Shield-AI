import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
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
        "CONFIDENTIAL SUPPLY CHAIN & LOGISTICS MANIFEST\n"
        "Vendor Organization: Acros Logistics Private Ltd | GSTIN: 27AABCU9603R1ZN\n"
        "Logistics Coordinator: Vikram Malhotra | Contact Email: vikram.malhotra@acroslogistics.in\n"
        "Dispatch Officer Phone: +91 9823011223 | Secondary Billing Phone: +91 9876543210\n"
        "Corporate Identity PAN: AABCA5432K | Aadhaar Representative: 4521 8901 2345\n"
        "Primary Freight Credit Card: 4532 8900 1234 5678\n\n"
        "Shipment Specifications:\n"
        "Purchase Order PO-89210 containing 1,500 units of semiconductor microcontrollers dispatched via Nhava Sheva Port."
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
