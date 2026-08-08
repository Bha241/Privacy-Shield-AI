"""
PrivacyShieldAI - Document Classifier & Persona Assignment Module
Detects document types (e.g. Master Service Agreement, Invoice, Medical Record, etc.)
and automatically assigns an expert AI persona (e.g. Legal Contract Analyst, Financial Auditor, HR Specialist).
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any


@dataclass
class ClassificationResult:
    doc_type: str
    persona: str
    confidence: float
    key_terms_matched: List[str] = field(default_factory=list)


class DocumentClassifier:
    """
    Lightweight, high-performance document type classifier and persona assignment engine.
    Analyzes document headers, structural keywords, and domain terminology.
    """

    DOCUMENT_PROFILES: Dict[str, Dict[str, Any]] = {
        "Master Service Agreement": {
            "persona": "Legal Contract Analyst",
            "keywords": [
                r"\bmaster service[s]? agreement\b", r"\bmsa\b", r"\bterms and conditions\b",
                r"\bservice level agreement\b", r"\bindemnification\b", r"\bgoverning law\b",
                r"\btermination for cause\b", r"\blimitation of liability\b", r"\bcontractual obligations\b"
            ]
        },
        "Employment Contract": {
            "persona": "Legal Contract Analyst",
            "keywords": [
                r"\bemployment agreement\b", r"\bemployment contract\b", r"\boffer letter\b",
                r"\bprobationary period\b", r"\bemployee duties\b", r"\btermination of employment\b"
            ]
        },
        "Employee Onboarding Form": {
            "persona": "HR Specialist",
            "keywords": [
                r"\bemployee onboarding\b", r"\bonboarding registration\b", r"\bnew hire form\b",
                r"\bemployee registration\b", r"\bjoining form\b", r"\bemergency contact\b",
                r"\bdate of joining\b", r"\breporting manager\b", r"\bdepartment\b"
            ]
        },
        "Invoice": {
            "persona": "Financial Auditor",
            "keywords": [
                r"\binvoice\b", r"\btax invoice\b", r"\bbill to\b", r"\bship to\b",
                r"\binvoice number\b", r"\bdue date\b", r"\bsubtotal\b", r"\bgrand total\b",
                r"\bvat\b", r"\bgst\b", r"\bpayment terms\b"
            ]
        },
        "Purchase Order": {
            "persona": "Financial Auditor",
            "keywords": [
                r"\bpurchase order\b", r"\bpo number\b", r"\bvendor details\b",
                r"\bitem description\b", r"\bunit price\b", r"\bquantity\b", r"\bshipment terms\b"
            ]
        },
        "NDA": {
            "persona": "Legal Contract Analyst",
            "keywords": [
                r"\bnon[\-\s]?disclosure agreement\b", r"\bnda\b", r"\bconfidentiality agreement\b",
                r"\bproprietary information\b", r"\breceiving party\b", r"\bdisclosing party\b"
            ]
        },
        "Passport": {
            "persona": "Identity Verification Specialist",
            "keywords": [
                r"\bpassport\b", r"\brepublic of\b", r"\bpassport no\b", r"\bsurname\b",
                r"\bgiven names\b", r"\bnationality\b", r"\bdate of birth\b", r"\bdate of expiry\b"
            ]
        },
        "Driving License": {
            "persona": "Identity Verification Specialist",
            "keywords": [
                r"\bdriving licen[sc]e\b", r"\bdl number\b", r"\blicensed to drive\b",
                r"\btransport department\b", r"\bvehicle class\b"
            ]
        },
        "Medical Record": {
            "persona": "Clinical Documentation Specialist",
            "keywords": [
                r"\bpatient clinical report\b", r"\bmedical evaluation\b", r"\bdiagnosis\b",
                r"\battending physician\b", r"\bclinical notes\b", r"\btreatment plan\b",
                r"\bhospital\b", r"\bprescription\b", r"\bsymptoms\b", r"\blab report\b"
            ]
        },
        "Insurance Policy": {
            "persona": "Insurance Advisor",
            "keywords": [
                r"\binsurance policy\b", r"\bpolicy schedule\b", r"\bpremium amount\b",
                r"\binsured person\b", r"\bclaim procedure\b", r"\bdeductible\b", r"\bcoverage\b"
            ]
        },
        "Bank Statement": {
            "persona": "Financial Analyst",
            "keywords": [
                r"\bbank statement\b", r"\baccount statement\b", r"\bopening balance\b",
                r"\bclosing balance\b", r"\btransaction history\b", r"\bdeposit\b", r"\bwithdrawal\b"
            ]
        },
        "Financial Report": {
            "persona": "Financial Analyst",
            "keywords": [
                r"\bbalance sheet\b", r"\bincome statement\b", r"\bprofit and loss\b",
                r"\bcash flow statement\b", r"\bfinancial report\b", r"\bfiscal year\b"
            ]
        },
        "Resume": {
            "persona": "HR Specialist",
            "keywords": [
                r"\bcurriculum vitae\b", r"\bresume\b", r"\bprofessional summary\b",
                r"\bwork experience\b", r"\beducation\b", r"\bskills\b", r"\bprojects\b"
            ]
        },
        "Research Paper": {
            "persona": "Research Analyst",
            "keywords": [
                r"\babstract\b", r"\bintroduction\b", r"\bmethodology\b", r"\bexperimental results\b",
                r"\bdiscussion\b", r"\breferences\b", r"\bconclusion\b"
            ]
        },
        "Tax Document": {
            "persona": "Financial Analyst",
            "keywords": [
                r"\btax return\b", r"\bform 16\b", r"\bincome tax\b", r"\btaxable income\b",
                r"\bassessment year\b", r"\btds\b"
            ]
        },
        "Government Form": {
            "persona": "Identity Verification Specialist",
            "keywords": [
                r"\bgovernment of\b", r"\baadhaar\b", r"\bpan card\b", r"\bvoter id\b",
                r"\bofficial form\b", r"\bdepartment of\b"
            ]
        },
        "Utility Bill": {
            "persona": "Senior Document Analyst",
            "keywords": [
                r"\belectricity bill\b", r"\bwater bill\b", r"\bgas bill\b", r"\bconsumer number\b",
                r"\bbilling cycle\b", r"\bdue amount\b"
            ]
        },
    }

    @classmethod
    def classify(cls, text: str) -> ClassificationResult:
        """
        Classifies document text into a specific type and persona.
        Falls back to 'Unknown' and 'Senior Document Analyst' if confidence is low.
        """
        if not text or not text.strip():
            return ClassificationResult(
                doc_type="Unknown",
                persona="Senior Document Analyst",
                confidence=0.5,
                key_terms_matched=[]
            )

        text_lower = text.lower()[:3000]  # Focus analysis on header & body

        best_doc_type = "Unknown"
        best_persona = "Senior Document Analyst"
        best_score = 0.0
        best_terms: List[str] = []

        for doc_type, profile in cls.DOCUMENT_PROFILES.items():
            matched_terms = []
            score = 0.0

            for pattern in profile["keywords"]:
                if re.search(pattern, text_lower, flags=re.IGNORECASE):
                    matched_terms.append(pattern.replace(r"\b", "").replace(r"[\-\s]?", " "))
                    score += 0.25

            if score > best_score:
                best_score = score
                best_doc_type = doc_type
                best_persona = profile["persona"]
                best_terms = matched_terms

        confidence = round(min(1.0, max(0.5, best_score)), 2)

        return ClassificationResult(
            doc_type=best_doc_type,
            persona=best_persona,
            confidence=confidence,
            key_terms_matched=best_terms
        )
