from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class PIIRedactRequest(BaseModel):
    text: str
    masking_strategy: Optional[str] = "REPLACE"  # REPLACE, HASH, ANONYMIZE
    custom_entities: Optional[List[str]] = None

class EntityMatch(BaseModel):
    entity_type: str
    text: str
    start: int
    end: int
    score: float

class DocumentClassification(BaseModel):
    category: str
    sensitivity: str
    confidence: float
    summary: str
    compliance_frameworks: List[str]

class PIIRedactResponse(BaseModel):
    original_text: str
    redacted_text: str
    entities: List[EntityMatch]
    risk_score: int
    risk_level: str
    compliance_passed: bool
    classification: Optional[DocumentClassification] = None

class LLMSettings(BaseModel):
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 1024
    model: str = "Llama-3-70b-PrivacyGuard"

class ChatMessageRequest(BaseModel):
    message: str
    original_text: Optional[str] = ""
    redacted_text: Optional[str] = ""
    entities: Optional[List[EntityMatch]] = None
    document_id: Optional[str] = None
    file_name: Optional[str] = None
    llm_settings: Optional[LLMSettings] = None

class ChatMessageResponse(BaseModel):
    masked_response: str
    demasked_response: str
    sources_retrieved: List[str]
    model_used: str
    processing_time_ms: int
    provider_used: Optional[str] = "Groq"
    routing_strategy: Optional[str] = "Cloud"
    fallback_reason: Optional[str] = None
    latency_ms: Optional[int] = None
    request_id: Optional[str] = None

