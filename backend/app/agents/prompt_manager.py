"""
PrivacyShieldAI - Prompt Manager Module (v3.0 Strategic AI Analyst Prompt Engine)
Provides reasoning-oriented Chain-of-Thought prompts, persona integration, dynamic summary modes,
and high-quality few-shot examples for ChatGPT / Claude / Gemini level document intelligence.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class PromptSpec:
    intent: str
    system_prompt: str
    writing_style: str
    output_instructions: str
    few_shot_examples: List[Dict[str, str]] = field(default_factory=list)


class PromptManager:
    """
    Constructs reasoning-oriented, persona-aware, consultant-grade system prompts.
    Eliminates robotic AI cliches, supports multiple summary modes, and provides Chain-of-Thought guidance.
    """

    # Summary modes mapping target length and tone
    SUMMARY_MODES: Dict[str, Dict[str, str]] = {
        "short": {
            "name": "Short Summary",
            "instruction": "Provide a concise summary (~75 words) highlighting the single core purpose and key outcome."
        },
        "executive": {
            "name": "Executive Summary",
            "instruction": "Provide a strategic executive summary (~150 words) tailored for C-level leadership."
        },
        "detailed": {
            "name": "Detailed Summary",
            "instruction": "Provide a comprehensive summary (~350 words) thoroughly covering purpose, obligations, and key terms."
        },
        "technical": {
            "name": "Technical Summary",
            "instruction": "Focus on technical architecture, system specs, parameters, and operational protocols."
        },
        "business": {
            "name": "Business Summary",
            "instruction": "Focus on commercial terms, market implications, operational scope, and financial impact."
        },
        "legal": {
            "name": "Legal Summary",
            "instruction": "Focus on legal obligations, terms, indemnification, liability, and governing frameworks."
        },
        "compliance": {
            "name": "Compliance Summary",
            "instruction": "Focus on regulatory adherence, DPDP requirements, consent, and data protection safeguards."
        },
    }

    # High-quality few-shot examples across major document types
    FEW_SHOT_LIBRARY: Dict[str, Dict[str, str]] = {
        "Master Service Agreement": {
            "user": "Summarize this agreement.",
            "assistant": (
                "This Master Service Agreement establishes the commercial framework governing technical infrastructure "
                "services between the provider and client. It defines operational commitments, payment milestones, "
                "liability limits, and confidentiality protocols for all current and future service engagements.\n\n"
                "The contract outlines key risk controls including mutual indemnification for data breaches, strict non-disclosure "
                "clauses, and defined SLA uptime guarantees. Key corporate contact details and official identity tokens "
                "(<ORGANIZATION_1>, <REGISTRATION_1>) are recorded under restricted access terms.\n\n"
                "The agreement provides a legal foundation for service execution while enforcing data privacy compliance."
            )
        },
        "Invoice": {
            "user": "Summarize this invoice.",
            "assistant": (
                "Tax Invoice <INVOICE_1> records billing for cloud computing resources and enterprise software licenses "
                "issued to <ORGANIZATION_1> for the billing cycle ending August 2026. The total payable amount is set "
                "under net-30 settlement terms.\n\n"
                "Line items include managed server instances, database storage, and premium support tiers. Tax registration "
                "numbers (<GSTIN_1>) and corporate banking coordinates (<BANK_ACCOUNT_1>) are specified for payment processing."
            )
        },
        "Employee Onboarding Form": {
            "user": "Summarize this employee onboarding document.",
            "assistant": (
                "This onboarding registration form registers a newly appointed Senior AI Systems Engineer within the Cloud "
                "Solutions department at Apex Global Technologies Ltd. It establishes official employment records, reporting "
                "hierarchies under Rahul Sharma, joining timelines, and facility assignment at the Tech Park Campus in Bangalore.\n\n"
                "Personal identification credentials including national identity numbers (<AADHAAR_1>, <PAN_1>), contact details "
                "(<PHONE_1>), and emergency references (<NAME_1>) are recorded under encrypted administrative storage.\n\n"
                "The form completes administrative setup while enforcing employee consent to corporate privacy standards."
            )
        },
        "Medical Record": {
            "user": "Summarize this clinical report.",
            "assistant": (
                "This outpatient clinical evaluation documents the diagnostic assessment and treatment regimen prescribed for "
                "an acute respiratory condition. Dr. Robert Vance evaluated symptoms of persistent cough and secondary fever, "
                "ordering diagnostic chest imaging and inflammatory marker blood panels.\n\n"
                "Treatment includes a 5-day course of targeted oral antibiotics alongside supportive therapy, with a scheduled "
                "follow-up review in seven days. Sensitive patient identifiers (<NAME_1>, <AADHAAR_1>) remain protected under "
                "medical record privacy safeguards."
            )
        },
        "Research Paper": {
            "user": "Summarize this research paper.",
            "assistant": (
                "This paper presents a novel algorithmic approach to privacy-preserving retrieval augmented generation (RAG) "
                "for large language models. The authors demonstrate that tokenizing sensitive entities prior to cloud inference "
                "eliminates data leakage while maintaining high semantic accuracy across benchmark evaluation datasets.\n\n"
                "Experimental findings confirm a 98.4% accuracy retention in complex document query tasks compared to unmasked "
                "baseline architectures, offering a viable blueprint for enterprise privacy deployment."
            )
        },
        "Financial Statement": {
            "user": "Summarize this financial report.",
            "assistant": (
                "The quarterly financial report records strong revenue growth driven by cloud software subscriptions, with gross "
                "operating margins expanding by 14% year-over-year. Capital expenditure remained aligned with strategic targets "
                "for infrastructure expansion.\n\n"
                "Key financial risks include currency exchange fluctuations and increased compliance overhead. Cash reserves "
                "remain sufficient to support planned expansion without short-term debt financing."
            )
        },
        "NDA": {
            "user": "Summarize this NDA.",
            "assistant": (
                "This Non-Disclosure Agreement governs the mutual exchange of proprietary technical and financial information "
                "during strategic partnership evaluations. It establishes a 5-year confidentiality obligation, restricting "
                "information access strictly to designated representatives.\n\n"
                "The agreement excludes publicly known information and mandates prompt return or destruction of confidential "
                "materials upon termination of discussions."
            )
        },
    }

    @classmethod
    def determine_summary_mode(cls, query: str, default_mode: str = "executive") -> str:
        """Determines best summary mode based on query terms."""
        q_lower = query.lower()
        if "short" in q_lower or "brief" in q_lower or "tl;dr" in q_lower or "75 words" in q_lower:
            return "short"
        if "detailed" in q_lower or "thorough" in q_lower or "in-depth" in q_lower or "full summary" in q_lower:
            return "detailed"
        if "technical" in q_lower or "architecture" in q_lower or "spec" in q_lower:
            return "technical"
        if "business" in q_lower or "commercial" in q_lower or "market" in q_lower:
            return "business"
        if "legal" in q_lower or "contractual" in q_lower or "liability" in q_lower:
            return "legal"
        if "compliance" in q_lower or "privacy" in q_lower or "dpdp" in q_lower or "gdpr" in q_lower:
            return "compliance"
        return default_mode

    @classmethod
    def build_system_prompt(
        cls,
        intent: str,
        context: str,
        doc_type: str = "Unknown",
        persona: str = "Senior Document Analyst",
        query: str = "",
        summary_mode: Optional[str] = None
    ) -> str:
        """
        Constructs persona-guided, Chain-of-Thought system prompt.
        Encourages expert consulting prose while strictly forbidding AI cliches.
        """
        mode = summary_mode or cls.determine_summary_mode(query)
        mode_info = cls.SUMMARY_MODES.get(mode, cls.SUMMARY_MODES["executive"])

        few_shot = cls.FEW_SHOT_LIBRARY.get(doc_type) or cls.FEW_SHOT_LIBRARY["Master Service Agreement"]
        few_shot_str = f"\n=== EXEMPLAR RESPONSE STYLE ({doc_type}) ===\nUser: {few_shot['user']}\nResponse:\n{few_shot['assistant']}\n"

        cot_reasoning_instructions = (
            "INTERNAL REASONING STEPS (Perform silently before responding):\n"
            "1. Identify document context & core objective.\n"
            "2. Determine primary audience & business/legal/clinical significance.\n"
            "3. Isolate key operational data and sensitive identity markers.\n"
            "4. Formulate clear, narrative-driven conclusions without robotic label dumping.\n"
            "DO NOT output internal reasoning or thought tags. Output ONLY the final polished response."
        )

        style_rules = (
            "STRICT WRITING & STYLE RULES:\n"
            "1. You are reading the complete active document. Understand the document before writing. Explain it naturally.\n"
            "2. FORBID ROBOTIC DISCLAIMERS & AI CLICHES:\n"
            "   - NEVER say 'Based on available document excerpts...', 'Based on retrieved context...', 'The available context indicates...', or 'I don't have enough context'\n"
            "   - NEVER mention vector retrieval, excerpts, context chunks, or search mechanics.\n"
            "   - NEVER start with 'This document is designed to...', 'The primary purpose of this document is...', or 'This document contains...'\n"
            "   - NEVER use overused AI transitions: 'Additionally', 'Furthermore', 'Moreover', 'Overall', 'In conclusion'\n"
            "   - NEVER output robotic labels like 'Document Header', 'Key Information', 'Privacy Summary', 'Detected PII'\n"
            "3. DYNAMIC PARAGRAPHS: Do NOT force a rigid paragraph template. Write paragraphs dynamically based on document complexity (2, 3, 4, or 6 paragraphs).\n"
            "4. PRESERVE ALL MASKED TOKENS: Keep tokens (<NAME_1>, <PAN_1>, <AADHAAR_1>, etc.) EXACTLY as they appear.\n"
            "5. NO HALLUCINATION: Rely strictly on sanitized context."
        )

        intent_instructions = ""
        if intent == "summary":
            intent_instructions = f"TASK: Generate a {mode_info['name']}. {mode_info['instruction']}"
        elif intent == "analysis":
            intent_instructions = (
                "TASK: Perform a strategic document analysis. Structure response naturally with: "
                "Observations, Business Impact, and Strategic Recommendations."
            )
        elif intent == "compliance":
            intent_instructions = (
                "TASK: Perform a regulatory compliance evaluation. Structure response naturally with: "
                "Key Findings, Compliance & Privacy Risks, and Mitigation Recommendations."
            )
        elif intent == "question":
            intent_instructions = (
                "TASK: Direct Question Answering. Answer the user's specific question directly in the first sentence. "
                "Follow with a concise supporting explanation. Do NOT generate unsolicited document summaries."
            )
        elif intent == "comparison":
            intent_instructions = (
                "TASK: Comparative Analysis. Provide a Markdown table highlighting key differences, "
                "followed by structural comparison observations."
            )
        else:
            intent_instructions = "TASK: Provide expert document intelligence analysis."

        system_prompt = f"""You are PrivacyShieldAI acting as a {persona}.

Document Category: {doc_type}
Target Mode: {mode_info['name']}

{cot_reasoning_instructions}

{intent_instructions}

{style_rules}
{few_shot_str}
=== SANITIZED DOCUMENT CONTEXT ===
{context}
"""
        return system_prompt

    @classmethod
    def build_messages(
        cls,
        intent: str,
        context: str,
        query: str,
        doc_type: str = "Unknown",
        persona: str = "Senior Document Analyst",
        history: Optional[List[Dict[str, str]]] = None,
        summary_mode: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """Builds chat messages array for Groq / OpenAI completion APIs."""
        system_prompt = cls.build_system_prompt(
            intent=intent,
            context=context,
            doc_type=doc_type,
            persona=persona,
            query=query,
            summary_mode=summary_mode
        )
        messages = [{"role": "system", "content": system_prompt}]

        if history:
            for msg in history[-10:]:
                if isinstance(msg, dict) and msg.get("role") and msg.get("content"):
                    r = msg["role"]
                    c = str(msg["content"]).strip()
                    if r in ["user", "assistant"] and c:
                        messages.append({"role": r, "content": c})

        messages.append({"role": "user", "content": query})
        return messages
