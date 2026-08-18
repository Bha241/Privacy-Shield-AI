# PrivacyShield AI - Evaluation & Regression Framework

A production-grade evaluation system for PrivacyShield AI comprising:
1. **Custom Privacy Leakage Detection** (Indian + global raw PII regex audit)
2. **RAGAS Answer Quality Evaluation** (Faithfulness, Answer Relevancy, Context Precision, Context Recall)
3. **Promptfoo Regression Test Suite** (LLM safety, prompt robustness, and adversarial jailbreak resistance)
4. **Unified CLI Evaluation Runner** (`run_eval.py`)

---

## Directory Structure

```text
backend/eval/
├── datasets/
│   ├── privacy_eval.jsonl       # 10 realistic test cases (identity, PII extraction, jailbreaks)
│   └── rag_eval.jsonl           # RAGAS ground-truth evaluation dataset
├── leakage/
│   ├── __init__.py
│   ├── pii_patterns.py          # Regex patterns for Indian & global PII (PHONE, PAN, AADHAAR, etc.)
│   └── leakage_checker.py       # find_raw_pii(), leakage_report(), assert_no_leakage()
├── promptfoo/
│   ├── promptfooconfig.yaml     # Promptfoo test suite configuration & regex assertions
│   └── prompts/
│       └── privacy_rag_system.txt # Masked-token system prompt
├── ragas_eval.py                # Standalone & package RAGAS metric evaluator
├── run_eval.py                  # Unified CLI orchestrator
└── README.md                    # Documentation & guide
```

---

## 1. Custom Privacy Leakage Testing

The leakage checker scans text to guarantee **zero raw PII** is sent in LLM context or leaked in the final response.

### Supported PII Entities
- **PHONE**: Indian mobiles (`+91 98201 44556`), landlines (`022-45678901`), international numbers
- **EMAIL**: Standard RFC-compliant email addresses
- **PAN**: Indian Permanent Account Numbers (`[A-Z]{5}[0-9]{4}[A-Z]`)
- **AADHAAR**: 12-digit Indian UIDAI numbers with space/hyphen delimiters
- **GSTIN**: 15-character Goods and Services Tax numbers
- **UPI**: UPI handles (`name@okaxis`, `user@okhdfcbank`, `mobile@paytm`, `user@upi`)
- **PASSPORT**, **CREDIT_CARD**, **IFSC**, **BANK_ACCOUNT**

Masked tokens such as `[PHONE_1]`, `[PAN_1]`, `[EMAIL_1]`, `[NAME_1]` are recognized as valid safe placeholders and do **not** trigger false alarms.

### Programmatic Usage

```python
from eval.leakage import find_raw_pii, leakage_report, assert_no_leakage

# 1. Scan for raw PII entities
raw_hits = find_raw_pii("Contact Rajesh at +91 9820144556 or rajesh@example.com")
for hit in raw_hits:
    print(f"Detected {hit.entity_type}: {hit.raw_value} at {hit.start}:{hit.end}")

# 2. Check context vs answer leakage
report = leakage_report(
    context="Purchase Order PO-3391 for vendor [NAME_1] (Phone: [PHONE_1])",
    answer="The contact phone number is [PHONE_1]."
)

print(report["is_safe"])          # True
print(report["context_leakage"])  # False
print(report["answer_leakage"])   # False

# 3. Assert zero leakage in unit tests / pipelines
assert_no_leakage(context="[NAME_1] details", answer="The phone is [PHONE_1]")
```

---

## 2. RAG Quality Evaluation (RAGAS)

Evaluates the RAG pipeline across 4 standard metrics:
- **Faithfulness**: Verifies whether the answer is strictly grounded in retrieved context.
- **Answer Relevancy**: Evaluates how pertinent the answer is to the user's query.
- **Context Precision**: Determines whether relevant context chunks are ranked ahead of irrelevant chunks.
- **Context Recall**: Verifies that retrieved context captures all ground truth facts.

### Running RAGAS Evaluation

```bash
# Run standalone RAGAS evaluation
python eval/ragas_eval.py --dataset eval/datasets/rag_eval.jsonl --output eval/ragas_report.json
```

*Note: Includes an automatic deterministic fallback engine if the official `ragas` library or external API keys are unavailable.*

---

## 3. Promptfoo Regression Testing

Promptfoo is used for regression testing across cloud and local models to verify that raw PII is never generated and that masked reasoning works consistently.

### Running Promptfoo

```bash
cd eval/promptfoo

# Run evaluation with npx (no global install needed)
npx promptfoo eval -c promptfooconfig.yaml

# View visual report in browser
npx promptfoo view
```

---

## 4. Unified CLI Runner (`run_eval.py`)

Execute everything from a single command:

```bash
# Run full suite (Leakage + RAGAS in dry-run/mock mode)
python eval/run_eval.py --mode all --dry-run

# Run only privacy leakage tests
python eval/run_eval.py --mode leakage

# Run only RAGAS quality tests
python eval/run_eval.py --mode ragas

# Run live with Groq LLM (requires GROQ_API_KEY)
python eval/run_eval.py --mode all --model llama-3.3-70b-versatile
```

### Exit Codes for CI/CD Gates
- `0`: All tests passed with 100% privacy safety.
- `1`: Raw PII leakage detected or test failures encountered.

---

## Reusing in the Main RAG Pipeline

You can directly import the leakage checker inside `app/agents` or FastAPI middleware:

```python
from eval.leakage import assert_no_leakage, leakage_report

def rag_pipeline_response_guard(context: str, answer: str):
    report = leakage_report(context, answer)
    if not report["is_safe"]:
        # Log security audit violation & sanitize response
        return "Protected Response: Raw PII was detected and blocked by PrivacyShield Guard."
    return answer
```
