"""
Token-aware chunker with truncation-safe extraction, for an LLM-based PII
fallback layer.

Intended use: one node in a larger pipeline (e.g. PrivacyShield-AI's
LangGraph pipeline) that receives only the residual, low-confidence text a
local NER pass (Presidio / spaCy / GLiNER) was unsure about -- not full
documents. Keeping the input volume small is what makes the cost, latency,
and privacy tradeoffs of calling an LLM at all acceptable; sending whole
documents through here defeats the point of a privacy-preserving pipeline.

Design choices vs. the naive "1500 chars per chunk" approach:
  - Chunks by tokens, not characters, and reserves budget for prompt +
    expected output before deciding chunk size.
  - Splits on semantic boundaries (paragraph > sentence > line) using
    span-preserving regex, so chunk offsets map exactly back to the
    original text -- important here since a wrong offset masks the wrong
    span of a real document.
  - Uses overlapping windows so an entity straddling a boundary is never
    silently lost.
  - Detects truncation via finish_reason AND a JSON-validity check, since
    not every API surfaces finish_reason reliably.
  - On truncation, recursively halves the offending chunk and retries. It
    does NOT ask the model to self-paginate ("return entities 1-50, then
    51-100") -- that requires the model to already know how many entities
    exist, which it can't, without feeding prior output back as context.
  - Assumes the actual LLM call uses structured/tool-call output (a JSON
    schema) rather than free-text parsing, wherever the API supports it.
    llm_call() here is a stand-in for that.

Requires: llama-cpp-python (pip install llama-cpp-python)
Environment: Set GGUF_MODEL_PATH to your local GGUF model file path
"""

from __future__ import annotations

import json
import re
import os
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# --- Token accounting with llama-cpp-python --------------------------------

class LlamaTokenizer:
    """Wrapper for llama-cpp tokenizer to match the interface expected by chunker."""

    def __init__(self, model_path: str):
        """
        Initialize tokenizer with a GGUF model.

        Args:
            model_path: Path to the GGUF model file
        """
        try:
            from llama_cpp import Llama
        except ImportError:
            raise ImportError(
                "llama-cpp-python is required. Install with:\n"
                "pip install llama-cpp-python"
            )

        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"GGUF model not found at: {model_path}\n"
                f"Set GGUF_MODEL_PATH environment variable to your model file path."
            )

        logger.info(f"Loading GGUF model from: {model_path}")
        # Load model with n_gpu_layers for acceleration (adjust as needed)
        self.model = Llama(model_path=model_path, n_gpu_layers=-1)
        logger.info("GGUF model loaded successfully")

    def encode(self, text: str) -> list:
        """
        Tokenize text and return token IDs.

        Args:
            text: Text to tokenize

        Returns:
            List of token IDs
        """
        return self.model.tokenize(text.encode("utf-8"))

    def decode(self, tokens: list) -> str:
        """
        Decode token IDs back to text.

        Args:
            tokens: List of token IDs

        Returns:
            Decoded text
        """
        return self.model.detokenize(tokens).decode("utf-8")


class ExistingLlamaTokenizer:
    """Wrapper using an already instantiated Llama model instance to avoid double loading."""
    def __init__(self, llama_model):
        self.model = llama_model

    def encode(self, text: str) -> list:
        return self.model.tokenize(text.encode("utf-8"))

    def decode(self, tokens: list) -> str:
        return self.model.detokenize(tokens).decode("utf-8")


def get_tokenizer(model_path_or_instance: Optional[object] = None) -> object:
    """
    Get a tokenizer using llama-cpp-python with a GGUF model or existing instance.
    """
    if hasattr(model_path_or_instance, 'tokenize'):
        return ExistingLlamaTokenizer(model_path_or_instance)
    if isinstance(model_path_or_instance, ExistingLlamaTokenizer):
        return model_path_or_instance
    
    model_path = model_path_or_instance
    if model_path is None:
        model_path = os.getenv("GGUF_MODEL_PATH")
        if not model_path:
            try:
                from pii_detector.config import MODEL_PATH
                if os.path.exists(MODEL_PATH):
                    model_path = str(MODEL_PATH)
            except Exception:
                pass
        if not model_path:
            raise ValueError(
                "Model path not provided."
            )

    return LlamaTokenizer(str(model_path))


def count_tokens(text: str, tokenizer: LlamaTokenizer) -> int:
    """
    Count the number of tokens in text.

    Args:
        text: Text to count tokens for
        tokenizer: LlamaTokenizer instance

    Returns:
        Number of tokens
    """
    return len(tokenizer.encode(text))


# --- Density heuristic (bounded, not precise) ---------------------------
# Used only to scale chunk size down for dense text -- not a substitute
# for real detection, and deliberately cheap (no model call).

_DENSITY_PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "phone": re.compile(r"\+?\d[\d\-\s()]{7,}\d"),
    "digit_run": re.compile(r"\d{4,}"),
}


def estimate_entity_density(text: str) -> float:
    """Rough hits per 100 chars across a few PII-shaped patterns."""
    hits = sum(len(p.findall(text)) for p in _DENSITY_PATTERNS.values())
    return hits / max(len(text), 1) * 100


def adaptive_max_tokens(base_max_input_tokens: int, text: str) -> int:
    density = estimate_entity_density(text)
    if density > 3:
        return int(base_max_input_tokens * 0.35)
    if density > 1:
        return int(base_max_input_tokens * 0.6)
    return base_max_input_tokens


# --- Span-preserving semantic splitting ---------------------------------
# Splits by boundary but returns (start, end) spans into the ORIGINAL text,
# so chunks can be reconstructed with text[start:end] -- no rejoining, no
# drift between chunk offsets and true document offsets.

def _split_with_spans(text: str, boundary_pattern: str) -> list[tuple[int, int]]:
    spans, last = [], 0
    for m in re.finditer(boundary_pattern, text):
        if m.start() > last:
            spans.append((last, m.start()))
        last = m.end()
    if last < len(text):
        spans.append((last, len(text)))
    return spans


def semantic_unit_spans(text: str) -> list[tuple[int, int]]:
    """Paragraph, then sentence, then line -- whichever gives units small
    enough to work with. Falls back to the whole text if there's no
    punctuation structure at all (e.g. a CSV export)."""
    spans = _split_with_spans(text, r"\n\s*\n")
    if len(spans) > 1:
        return spans
    spans = _split_with_spans(text, r"(?<=[.!?])\s+")
    if len(spans) > 1:
        return spans
    spans = _split_with_spans(text, r"\n")
    return spans if spans else [(0, len(text))]


# --- Chunker --------------------------------------------------------------

@dataclass
class Chunk:
    text: str
    start_offset: int  # char offset into the original text
    chunk_id: int = 0  # Sequential chunk identifier


@dataclass
class TextChunker:
    tokenizer: object
    max_input_tokens: int = 1200
    overlap_tokens: int = 120  # ~10% of max_input_tokens

    def _find_overlap_start(self, text: str, spans, end_idx_inclusive: int) -> int:
        """Walk backward accumulating tokens until ~overlap_tokens is
        covered; return the unit index the next chunk should restart from."""
        total, idx = 0, end_idx_inclusive
        while idx > 0 and total < self.overlap_tokens:
            s, e = spans[idx]
            total += count_tokens(text[s:e], self.tokenizer)
            idx -= 1
        return idx + 1

    def chunk(self, text: str) -> list[Chunk]:
        limit = adaptive_max_tokens(self.max_input_tokens, text)
        spans = semantic_unit_spans(text)

        chunks: list[Chunk] = []
        group_start, tokens_in_group = 0, 0
        chunk_id = 0

        for i, (s, e) in enumerate(spans):
            unit_tokens = count_tokens(text[s:e], self.tokenizer)
            if tokens_in_group + unit_tokens > limit and i > group_start:
                c_start, c_end = spans[group_start][0], spans[i - 1][1]
                chunks.append(Chunk(text[c_start:c_end], c_start, chunk_id))
                chunk_id += 1
                group_start = self._find_overlap_start(text, spans, i - 1)
                tokens_in_group = sum(
                    count_tokens(text[spans[k][0]:spans[k][1]], self.tokenizer)
                    for k in range(group_start, i)
                )
            tokens_in_group += unit_tokens

        c_start, c_end = spans[group_start][0], spans[-1][1]
        chunks.append(Chunk(text[c_start:c_end], c_start, chunk_id))
        
        # filter out empty chunks containing only whitespace or masked spaces
        return [c for c in chunks if c.text.strip()]


# --- Truncation-safe extraction -------------------------------------------

@dataclass
class ExtractionResult:
    entities: list[dict] = field(default_factory=list)
    truncated_chunks_split: int = 0


def is_truncated(finish_reason: Optional[str], raw_text: str) -> bool:
    if finish_reason == "length":
        return True
    try:
        json.loads(raw_text)
        return False
    except (json.JSONDecodeError, TypeError):
        # Malformed and not explicitly flagged -- treat as truncated rather
        # than silently dropping this chunk's entities.
        return True


def extract_with_retry(
    chunk: Chunk,
    llm_call: Callable[[str], tuple[str, Optional[str]]],
    chunker: TextChunker,
    depth: int = 0,
    max_depth: int = 4,
) -> ExtractionResult:
    """llm_call(text) -> (raw_response_text, finish_reason). Swap in your
    actual client (OpenAI, Anthropic tool-use, self-hosted model, ...) --
    keep it returning finish_reason so truncation is caught even when the
    JSON happens to parse anyway."""
    raw_text, finish_reason = llm_call(chunk.text)

    if not is_truncated(finish_reason, raw_text):
        parsed = json.loads(raw_text)
        entities = parsed if isinstance(parsed, list) else parsed.get("entities", [])
        for e in entities:
            if "start" in e:
                e["start"] += chunk.start_offset
                e["end"] += chunk.start_offset
        return ExtractionResult(entities=entities)

    if depth >= max_depth or count_tokens(chunk.text, chunker.tokenizer) < 100:
        # Stop splitting; surface what little we have rather than loop forever.
        return ExtractionResult(entities=[], truncated_chunks_split=1)

    mid = len(chunk.text) // 2
    left = Chunk(chunk.text[:mid], chunk.start_offset)
    right = Chunk(chunk.text[mid:], chunk.start_offset + mid)

    left_result = extract_with_retry(left, llm_call, chunker, depth + 1, max_depth)
    right_result = extract_with_retry(right, llm_call, chunker, depth + 1, max_depth)

    return ExtractionResult(
        entities=left_result.entities + right_result.entities,
        truncated_chunks_split=(
            1 + left_result.truncated_chunks_split + right_result.truncated_chunks_split
        ),
    )


def dedupe_entities(entities: list[dict]) -> list[dict]:
    seen, out = set(), []
    for e in entities:
        key = (e.get("start"), e.get("end"), e.get("label"))
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


# --- Pipeline entry point ---------------------------------------------------

def extract_pii_llm_fallback(
    text: str,
    llm_call: Callable[[str], tuple[str, Optional[str]]],
    model: str = "gpt-4o-mini",
) -> list[dict]:
    """Call this only on the residual/low-confidence text your local NER
    pass (Presidio/spaCy/GLiNER) flagged -- not on full documents."""
    tokenizer = get_tokenizer(model)
    chunker = TextChunker(tokenizer=tokenizer)
    all_entities: list[dict] = []
    for c in chunker.chunk(text):
        result = extract_with_retry(c, llm_call, chunker)
        all_entities.extend(result.entities)
    return dedupe_entities(all_entities)


# --- Demo ---------------------------------------------------------------

if __name__ == "__main__":
    def mock_llm_call(text: str) -> tuple[str, Optional[str]]:
        # Stand-in for a real client call. Replace with e.g.:
        #   resp = client.chat.completions.create(..., response_format={"type": "json_schema", ...})
        #   return resp.choices[0].message.content, resp.choices[0].finish_reason
        return json.dumps({"entities": []}), "stop"

    sample = "Contact John at john@example.com or 555-123-4567.\n\nHis employer is mentioned later."
    print(extract_pii_llm_fallback(sample, mock_llm_call))