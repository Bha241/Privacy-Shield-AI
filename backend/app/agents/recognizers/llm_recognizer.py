import json
import re
import logging
from pathlib import Path
from typing import List, Optional

from pii_detector.config import MODEL_PATH, N_CTX, N_THREADS, TEMPERATURE, MAX_TOKENS, N_GPU_LAYERS
from pii_detector.schemas.entities import Entity

logger = logging.getLogger(__name__)


class LLMRecognizer:
    """Strictly Local GGUF LLM Recognizer using Qwen 2.5 3B Instruct via llama-cpp-python for residual PII detection."""

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = Path(model_path) if model_path else MODEL_PATH
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            if not self.model_path.exists():
                logger.error(f"Local Qwen GGUF model not found at path: {self.model_path}")
                raise FileNotFoundError(f"Local Qwen GGUF model file not found: {self.model_path}")

            try:
                from llama_cpp import Llama
                logger.info(f"Loading local Qwen GGUF model from {self.model_path} (n_gpu_layers={N_GPU_LAYERS})")
                self._llm = Llama(
                    model_path=str(self.model_path),
                    n_ctx=N_CTX,
                    n_threads=N_THREADS,
                    n_gpu_layers=N_GPU_LAYERS,
                    verbose=False
                )
                logger.info("Local Qwen LLM successfully loaded into memory.")
            except Exception as e:
                logger.error(f"Failed to load local Qwen model: {e}")
                raise RuntimeError(f"Failed to load local Qwen LLM model: {e}") from e
        return self._llm

    def recognize(self, text: str) -> List[Entity]:
        if not text.strip():
            return []

        prompt = (
            "<|im_start|>system\n"
            "You are a precise PII (Personally Identifiable Information) recognition system. "
            "Scan the provided input text and extract all PII entities.\n"
            "Allowed entity types: NAME, DATE_OF_BIRTH, DATE, EMAIL, PHONE, ADDRESS, SSN, AADHAAR, PAN, FINANCIAL, MONEY, ORGANIZATION, LOCATION.\n"
            "Return valid JSON strictly matching this schema: {\"entities\": [{\"text\": \"...\", \"label\": \"...\"}]}\n"
            "<|im_end|>\n"
            f"<|im_start|>user\nInput Text:\n{text}\n<|im_end|>\n"
            "<|im_start|>assistant\n"
        )

        try:
            output = self.llm(
                prompt,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                stop=["<|im_end|>", "\n\n\n"]
            )
            raw_response = output["choices"][0]["text"].strip()

            json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
            if not json_match:
                return []

            data = json.loads(json_match.group(0))
            raw_entities = data.get("entities", [])
            if isinstance(data, list):
                raw_entities = data

            entities = []
            for item in raw_entities:
                val = item.get("text", "").strip()
                label = item.get("label", "PII").upper()
                if val and val in text:
                    match_pos = text.find(val)
                    start = match_pos if match_pos != -1 else 0
                    end = start + len(val) if match_pos != -1 else 0

                    entities.append(
                        Entity(
                            text=val,
                            label=label,
                            start=start,
                            end=end,
                            confidence=0.92,
                            source="llm_qwen2.5_local"
                        )
                    )
            return entities
        except Exception as e:
            logger.warning(f"Local Qwen LLM recognition notice: {e}")
            return []
