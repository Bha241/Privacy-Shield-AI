# Hybrid DPDP Compliance Engine

The **Hybrid DPDP Compliance Engine** is a multi-tier regulatory guardrail framework designed for PrivacyShield AI, aligning system actions with the **Digital Personal Data Protection (DPDP) Act 2023** and **DPDP Rules 2025**.

---

## 🏛️ Core Architectural Principle

> **Deterministic Rules ENFORCE. Local Qwen EXPLAINS.**
> 
> Hard security controls (e.g., zero raw PII to cloud, mandatory audit logging, child consent) are enforced deterministically in Python code. The LLM is **never** permitted to relax, override, or overturn a blocking security decision.

```
┌─────────────────────────────────────────────────────────────┐
│                    Incoming System Event                    │
│   (e.g., CLOUD_TRANSMISSION, DEMASKING, RETENTION, CHILD)   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│             Tier 1: Deterministic Rule Engine               │
│   • Zero Raw PII to Cloud (Section 8(5), Rule 6(1)(a))      │
│   • HITL Review Mandatory (Rule 3)                          │
│   • Child Data Parental Consent (Section 9, Rule 10)        │
│   • Immutable Audit Ledger (Section 8(4), Rule 12)          │
└──────────────┬───────────────────────────────┬──────────────┘
               │ Passed                        │ Blocked (Violation)
               ▼                               ▼
┌─────────────────────────────────────────────────────────────┐
│            Tier 2: DPDP Regulatory Retriever                │
│   • Semantic / Keyword Retrieval over DPDP Act & Rules      │
│   • Fetches exact section & rule citations                  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│            Tier 3: Local Qwen Legal Explainer               │
│   • Conservative, low-temperature (0.1) legal reasoning     │
│   • Cites statutory provisions ([DPDP_ACT_SEC_8_5])         │
│   • Guarantees final blocked status is preserved            │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 Structured GuardrailDecision                │
│   { is_compliant, blocked, risk_level, clauses, explanation }│
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 Package Structure

```text
app/agents/compliance/
├── __init__.py
├── dpdp_schemas.py            # DPDPClause, ComplianceEvent, GuardrailDecision
├── dpdp_rule_engine.py        # Deterministic statutory checks (Zero raw PII, HITL, Child data, Audit)
├── dpdp_retriever.py          # Semantic & keyword retrieval over DPDP regulations
├── dpdp_explainer_qwen.py     # Local Qwen conservative explanation synthesizer
├── dpdp_guardrails_engine.py  # Main orchestrator & FastAPI integration helper
├── dpdp_corpus/
│   ├── sample_act_chunks.jsonl   # Statutory clauses from DPDP Act 2023
│   └── sample_rules_chunks.jsonl # Safeguard rules from DPDP Rules 2025
└── README.md                  # Documentation & integration guide
```

---

## 🚀 Quickstart & Usage

### 1. Basic Python Usage

```python
from app.agents.compliance import get_dpdp_guardrails_engine, ComplianceEvent

engine = get_dpdp_guardrails_engine()

# Example 1: Evaluation of an unmasked cloud transmission attempt (Will be blocked)
unsafe_event = {
    "event_type": "CLOUD_TRANSMISSION",
    "raw_pii_to_cloud": True,          # Violation!
    "hitl_required": True,
    "hitl_approved": False,
    "has_child_data": False,
    "audit_written": True,
    "document_id": "doc_123",
    "actor_id": "usr_analyst"
}

decision = engine.evaluate_event(unsafe_event)

print(f"Is Compliant : {decision.is_compliant}")   # False
print(f"Blocked      : {decision.blocked}")        # True
print(f"Risk Level   : {decision.risk_level}")     # CRITICAL
print(f"Explanation  : {decision.explanation}")
# Output: "NON-COMPLIANT: Action 'CLOUD_TRANSMISSION' has been strictly BLOCKED by PrivacyShield DPDP Guardrails due to a CRITICAL risk violation..."
```

---

### 2. FastAPI Pipeline Integration

Protect endpoints before routing queries to LLMs or de-masking tokens:

```python
from fastapi import APIRouter, HTTPException, Depends
from app.agents.compliance import get_dpdp_guardrails_engine, ComplianceEvent

router = APIRouter()
guardrails_engine = get_dpdp_guardrails_engine()

@router.post("/api/v1/rag/query")
async def execute_privacy_rag(payload: dict):
    # 1. Build compliance event
    event = ComplianceEvent(
        event_type="CLOUD_TRANSMISSION",
        raw_pii_to_cloud=payload.get("contains_raw_pii", False),
        hitl_required=payload.get("hitl_required", False),
        hitl_approved=payload.get("hitl_approved", True),
        audit_written=True,
        document_id=payload.get("document_id")
    )
    
    # 2. Evaluate with DPDP Guardrails Engine
    decision = guardrails_engine.evaluate_event(event)
    
    # 3. Block unauthorized action immediately
    if decision.blocked:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "DPDP_COMPLIANCE_VIOLATION",
                "risk_level": decision.risk_level,
                "explanation": decision.explanation,
                "recommendations": decision.recommendations,
                "triggered_rules": decision.triggered_rules,
                "cited_clauses": [c.clause_id for c in decision.retrieved_clauses]
            }
        )
    
    # 4. Proceed safely with masked RAG pipeline
    return {"status": "SUCCESS", "data": "Processing query with verified DPDP compliance."}
```

---

## 📚 DPDP Corpus Indexing

The corpus files are stored in `dpdp_corpus/`:
- `sample_act_chunks.jsonl`: Contains key provisions from DPDP Act 2023 (Sections 4, 5, 6, 8(4), 8(5), 8(7), 9, 16).
- `sample_rules_chunks.jsonl`: Contains key technical safeguard rules from DPDP Rules 2025 (Rules 3, 6(1)(a), 6(1)(c), 8, 10, 12).

### To Index in Vector Database (Optional)
If a Chroma / pgvector store is configured, the `DPDPRegulationsRetriever` automatically attempts vector search over collection `dpdp_regulations`. If the vector database is offline, it gracefully uses the high-precision keyword/tag index without breaking execution.
