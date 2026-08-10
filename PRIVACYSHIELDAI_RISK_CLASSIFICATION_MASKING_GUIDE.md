# PrivacyShieldAI: Risk, Classification, and Masking Guide

This guide describes the current implementation of classification, risk assessment, Human-in-the-Loop (HITL) approval, masking, de-masking, persistence, and RAG ingestion. It is based on the code under backend/app and the current frontend components.

## 1. End-to-end flow

    Upload or paste document
            |
            v
    DocumentReader / OCR
            |
            v
    PII detection
            |
            +--> ClassificationAgent.classify_document()
            +--> RiskAgent.evaluate_risk()
            +--> DPDPGuardrailsEngine.evaluate_document_processing()
            +--> HITL review when required
            v
    MaskingAgent.apply_hitl_masking()
            |
            +--> tokenized masked text
            +--> document-scoped mapping
            +--> database persistence
            +--> masked-only RAG ingestion
            +--> audit event

The compiled LangGraph sequence is:

    read_and_detect
      -> classify_document
      -> evaluate_risk
      -> evaluate_dpdp
      -> hitl_review (conditional)
      -> apply_masking
      -> rag_ingestion
      -> log_audit

The direct FastAPI endpoints are the path used by the current frontend. /redact previews analysis; /mask applies approved entities, persists the result, and attempts masked-only RAG ingestion.

## 2. Source files

| Area | File | Responsibility |
|---|---|---|
| Classification | backend/app/agents/agents/classification_agent.py | Broad category and compliance-rule classification |
| Document type/persona | backend/app/agents/document_classifier.py | Specific profile and analyst persona |
| Risk | backend/app/agents/agents/risk_agent.py | Weighted risk score and HITL routing |
| Masking orchestration | backend/app/agents/agents/masking_agent.py | Converts approved candidates to internal entities |
| Masking engine | backend/app/agents/masking/pii_masker.py | Resolves spans, creates tokens, builds mappings |
| De-masking | backend/app/agents/agents/demasking_agent.py | Restores original values after approval |
| Agent workflow | backend/app/agents/graph/privacy_graph.py | LangGraph state, nodes, and routing |
| API integration | backend/app/api/v1/pii.py | /redact, /redact-file, /mask, and chat integration |
| API schemas | backend/app/schemas/pii.py | Request and response models |
| Persistence | backend/app/agents/db/models.py | Document and PII mapping database models |
| Live Redaction UI | frontend/src/components/LiveRedactionSection.tsx | Analyze, preview, and final masking UI |
| Chat/HITL UI | frontend/src/components/ChatSection.tsx | Upload, verification, preview, and confirmation |

## 3. Detector output consumed by these stages

Classification and risk consume entities produced by PII detection; they do not discover PII independently.

The detector uses one deterministic Fast pipeline: regex, spaCy, credential detection, and structured DOB/address detection.
- Credential detection covers passwords, API keys, bearer tokens, JWTs, private keys, and related secrets.
- Structured detection covers context-aware date-of-birth and address spans.

An internal entity contains text, label, start offset, end offset, confidence, and source. The API converts it to entity_type, text, start, end, and score. Offsets are important because masking replaces text by character range.

## 4. ClassificationAgent

File: backend/app/agents/agents/classification_agent.py

    ClassificationAgent.classify_document(text: str) -> Dict[str, Any]

This is the broad privacy/compliance classifier. It lowercases the complete input, counts whole-word keyword matches, selects the category with the highest count, and associates a compliance rule set.

Categories and example signals:

| Category | Signals |
|---|---|
| Financial | bank, PAN, account, invoice, statement, tax, salary, credit, debit, balance, amount, INR |
| Medical | patient, diagnosis, doctor, hospital, prescription, treatment, health, medical, blood, report |
| HR | employee, resume, designation, joining, performance, department, appraisal, salary, PF, experience |
| Legal | agreement, contract, clause, party, court, jurisdiction, affidavit, witness, legal, terms |

Algorithm:

1. Lowercase the text.
2. Count whole-word matches for every category.
3. Select the category with the highest count.
4. If every score is zero, use General with confidence 0.85.
5. Otherwise calculate:

       confidence = min(0.98, round(max_category_hits / total_hits + 0.5, 2))

6. Use DPDP_ACT_2025_RULES for Medical, Financial, and HR.
7. Use STANDARD_PRIVACY_RULES for other categories.
8. Set requires_manual_override when confidence is below 0.70.

Example return:

    {
      "category": "Financial",
      "confidence_score": 0.9,
      "compliance_rule_set": "DPDP_ACT_2025_RULES",
      "requires_manual_override": false
    }

This classifier is deterministic and does not call an LLM. It uses original text, not masked text.

## 5. DocumentClassifier: specific type and persona

File: backend/app/agents/document_classifier.py

    DocumentClassifier.classify(text: str) -> ClassificationResult

This classifier is separate from ClassificationAgent. It identifies a specific document profile and assigns a persona.

Profiles include Master Service Agreement, Employment Contract, Employee Onboarding Form, Invoice, Purchase Order, NDA, Passport, Driving License, Medical Record, Insurance Policy, Bank Statement, Financial Report, Resume, Research Paper, Tax Document, Government Form, and Utility Bill.

Algorithm:

1. Empty input returns Unknown, Senior Document Analyst, confidence 0.5.
2. Non-empty text is lowercased and limited to the first 3,000 characters.
3. Each profile contains regular-expression keywords.
4. Each matched pattern adds 0.25 to that profile score.
5. The highest-scoring profile wins.
6. Confidence is clamped between 0.5 and 1.0.
7. No match returns Unknown.

Example:

    ClassificationResult(
        doc_type="Purchase Order",
        persona="Financial Auditor",
        confidence=0.75,
        key_terms_matched=[...]
    )

This is for specific document intelligence and persona assignment. The current /redact response exposes the broader ClassificationAgent category.

## 6. RiskAgent

File: backend/app/agents/agents/risk_agent.py

    RiskAgent.evaluate_risk(
        document_category: str,
        detected_entities: List[Dict[str, Any]]
    ) -> Dict[str, Any]

RiskAgent turns detected PII into a score from 0 to 100, a Low/Medium/High category, and a HITL routing decision.

Entity weights:

| Label | Weight |
|---|---:|
| AADHAAR | 30 |
| PAN | 25 |
| FINANCIAL | 25 |
| MONEY | 20 |
| PHONE | 15 |
| EMAIL | 10 |
| NAME | 10 |
| DATE | 5 |
| ADDRESS | 15 |
| CUSTOM | 10 |

Unknown labels use the CUSTOM weight.

Category multipliers:

| Category | Multiplier |
|---|---:|
| Medical | 1.5 |
| Financial | 1.4 |
| HR | 1.2 |
| Legal | 1.1 |
| General | 1.0 |

Unknown categories use 1.0.

For each entity, the agent reads and uppercases label, adds its weight to base_score, and increments entity_type_counts. It then calculates:

    final_score = round(min(100.0, base_score * category_multiplier), 1)

High risk and route_to_hitl=true are set when score is at least 50, AADHAAR is present, PAN is present, or category is Medical/Financial.

Otherwise, score 20 through 49.9 is Medium and below 20 is Low.

Example return:

    {
      "risk_score": 72.0,
      "risk_category": "High",
      "route_to_hitl": true,
      "entity_type_counts": {"EMAIL": 1, "AADHAAR": 1},
      "rule_version": "2.0.0-SRS"
    }

The API also forces HITL for Medical, Financial, High, and Critical cases.

## 7. DPDP guardrails

File: backend/app/agents/agents/dpdp_guardrails.py

    DPDPGuardrailsEngine.evaluate_document_processing(
        raw_text,
        detected_entities,
        human_approved_count,
        total_entities_count
    )

This is separate from risk scoring. It returns compliance status, violations, passed rules, and recommendations. The graph stores these results before routing to HITL or masking. The /mask endpoint also runs this check and returns dpdp_compliant.

## 8. HITL review

HITL lets a human approve, reject, or edit candidates before final masking.

A candidate contains:

    {
      "id": 1,
      "text": "person@example.com",
      "label": "EMAIL",
      "start": 100,
      "end": 120,
      "confidence": 0.95,
      "approved": true,
      "user_custom_label": null
    }

Behavior:

- approved=true includes the candidate.
- approved=false excludes it.
- user_custom_label replaces the detector label.
- If HITL is required and no candidate is approved, /mask returns HTTP 403 unless force_mask=true.
- The graph review node uses supplied approvals; if none exist, it defaults to detected entities.

## 9. MaskingAgent

File: backend/app/agents/agents/masking_agent.py

    MaskingAgent(token_format="<{label}_{id}>")

Default tokens look like:

    <NAME_1>
    <EMAIL_1>
    <AADHAAR_1>

Function:

    apply_hitl_masking(raw_text, verified_entities) -> MaskedResult

Steps:

1. Iterate through HITL candidates.
2. Skip approved=false candidates.
3. Choose user_custom_label or label.
4. Normalize the label to uppercase and replace spaces with underscores.
5. Construct internal Entity objects with text, offsets, confidence, and source.
6. Call PIIMasker.mask with reuse_tokens=true.

Function:

    save_masked_outputs(file_stem, masked_result, output_dir)

This writes file_stem_masked.txt and file_stem_mapping.json. The database-backed /mask flow is the current primary persistence path.

## 10. PIIMasker engine

File: backend/app/agents/masking/pii_masker.py

Function _resolve_overlaps(entities):

1. Sort by start offset.
2. For equal starts, prefer the longer span.
3. Skip invalid spans where end <= start.
4. Skip spans that overlap an accepted span.

Function mask(text, entities, reuse_tokens=true):

1. Resolve overlapping spans.
2. Normalize each label to uppercase alphanumeric text.
3. Maintain counters per label.
4. Reuse a token for repeated identical label/value pairs when enabled.
5. Add token-to-original-value data to mapping.
6. Add metadata to detailed_mapping.
7. Replace spans from right to left so offsets remain valid.
8. Return masked_text, mapping, and detailed_mapping.

Detailed mapping record:

    {
      "mask_token": "<EMAIL_1>",
      "original_text": "person@example.com",
      "label": "EMAIL",
      "start": 100,
      "end": 120,
      "confidence": 0.95,
      "source": "regex"
    }

Function unmask(masked_text, mapping) replaces each token with its mapped original value. This is reversible substitution, not irreversible anonymization.

## 11. De-masking

File: backend/app/agents/agents/demasking_agent.py

    demask_text(masked_text, mapping, user_approved=True) -> Dict[str, Any]

- If approval is false, return masked text with status blocked.
- If approved, call PIIMasker.unmask.
- Return restored text, tokens replaced, replacement count, and status.

The mapping is the security boundary for restoration. Without it, tokens remain masked.

## 12. /api/v1/pii/redact

Request:

    {
      "text": "text to analyze",
      "masking_strategy": "REPLACE",
      "custom_entities": []
    }

Processing:

1. Reject empty text with HTTP 400.
2. Run the configured detector.
3. Convert internal entities to EntityMatch objects.
4. Create a masked preview with the masker.
5. If the advanced detector fails, use endpoint fallback regex patterns.
6. Classify original text with ClassificationAgent.
7. Evaluate risk.
8. Force HITL for sensitive/high-risk cases.
9. Write a detection audit event when available.
10. Return original text, masked preview, entities, risk, compliance, and classification.

It does not automatically ingest into RAG when HITL is required. Final ingestion belongs to /mask.

## 13. /api/v1/pii/redact-file

1. Read uploaded bytes.
2. Write a short-lived file under backend/temp_uploads.
3. Use DocumentReader(enable_ocr=True).
4. Delete the temporary file in a finally block when possible.
5. Reject empty extraction.
6. Call the same redact function used by pasted text.

File and pasted-text inputs therefore converge on the same classification, risk, and masking-preview logic.

## 14. /api/v1/pii/mask

Request:

    {
      "document_id": "stable-document-id",
      "original_text": "...",
      "approved_entities": [
        {
          "text": "person@example.com",
          "label": "EMAIL",
          "start": 10,
          "end": 30,
          "confidence": 0.95,
          "approved": true
        }
      ],
      "actor_id": "usr_system",
      "organization_id": "org_default",
      "force_mask": false
    }

Processing:

1. Ensure the document row exists; create it as PENDING if necessary.
2. Reclassify original text.
3. Recalculate risk using approved candidates.
4. Enforce HITL unless force_mask=true.
5. Mask only approved candidates.
6. Run DPDP guardrails.
7. Ingest only the masked result into document-scoped RAG.
8. Mark the document sanitized when ingestion succeeds.
9. Write a masking audit event without intentionally logging raw text.
10. Persist original text, masked text, token mapping, entity metadata, risk score, and category.
11. Replace existing PII mapping rows for that document.
12. Return masked result and ingestion status.

Persisted document data includes document ID, filename, original text, masked text, JSON mapping, entity metadata, status, risk score, and category. PII mapping rows are keyed by document ID and include token, entity type, original value, occurrence index, offsets, and approval state.

## 15. LangGraph workflow

PrivacyAgentState carries document identity, raw text, detected entities, category, risk, HITL state, DPDP results, masked text, token mapping, RAG status, and audit status.

Nodes:

- read_and_detect_node: runs PIIDetectionAgent on a file or raw text.
- classify_document_node: calls ClassificationAgent.
- evaluate_risk_node: calls RiskAgent.
- evaluate_dpdp_node: calls the DPDP engine.
- hitl_review_node: applies supplied approvals or detected candidates.
- apply_masking_node: calls MaskingAgent.
- rag_ingestion_node: handles the graph RAG stage and ingestion notices.
- log_audit_node: writes risk/category/compliance metadata and masked-token count.

route_after_risk_eval sends the workflow to HITL when route_to_hitl is true or the risk category is High and approval has not occurred. Otherwise it proceeds to masking.

## 16. Frontend behavior

Live Redaction, in frontend/src/components/LiveRedactionSection.tsx:

1. User pastes text or selects a file.
2. Calls redactPII or redactPIIFromFile.
3. Shows raw and masked output side by side.
4. Shows risk and classification.
5. Lets the user review entities.
6. Calls applyDocumentMasking for final persistence.

Chat, in frontend/src/components/ChatSection.tsx:

1. Registers or selects a document.
2. Shows the HITL verification modal.
3. Lets the user include or exclude entities.
4. Uses applyVerifiedHITLMasking for immediate local preview.
5. Calls applyDocumentMasking with the stable document ID.
6. The backend persists and indexes the masked representation.

The local preview is not authoritative for persistence. Backend /mask is authoritative.

## 17. Fallbacks and failure boundaries

- Detector unavailable: endpoint fallback regex patterns.
- Classification agent unavailable: simpler keyword fallback for Medical, Financial, and General.
- Risk agent unavailable: 22 multiplied by entity count, capped at 100, with threshold risk levels.
- Masking agent unavailable: fallback entity replacement and placeholder mapping.
- RAG ingestion fails: masking/database work can still return with ingested=false or failed state.
- Audit failure: warning is logged; masking response is not intentionally discarded.
- De-masking without approval: blocked.

## 18. Data-safety properties

- Masking is reversible only when the correct mapping is available and approval permits de-masking.
- Replacement is right-to-left to preserve offsets.
- Overlapping entities are resolved before replacement.
- Only approved HITL entities control final masking.
- RAG ingestion is intended to receive masked text, not raw text.
- Mappings and processed representations are stored with document IDs.
- Audit records store processing metadata rather than intentionally storing raw sensitive content.

## 19. Worked example

Input:

    Name: Alice Sharma
    Email: alice@example.com
    PAN: ABCDE1234F

Weights:

    NAME  = 10
    EMAIL = 10
    PAN   = 25
    base  = 45

For a Financial document, the multiplier is 1.4, producing 63.0. This is High risk and routes to HITL.

After approval:

    Name: <NAME_1>
    Email: <EMAIL_1>
    PAN: <PAN_1>

Mapping:

    {
      "<NAME_1>": "Alice Sharma",
      "<EMAIL_1>": "alice@example.com",
      "<PAN_1>": "ABCDE1234F"
    }

The masked representation is intended for RAG. The mapping is retained for controlled response de-masking.

## 20. Current implementation notes

- ClassificationAgent and DocumentClassifier are different classifiers with different outputs and purposes.
- Risk scoring is weighted rule logic, not an LLM judgment.
- /redact previews analysis; /mask performs approved persistence and ingestion.
- masking_strategy exists in the request contract, while the current agentic path uses reversible token replacement.
- PII detection has a single Fast pipeline; there is no separate semantic-model mode or PII-model settings endpoint.
- Fallbacks keep the application usable when optional agents/services are unavailable, but have less coverage than the primary path and should be monitored.
