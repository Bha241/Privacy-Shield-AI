import logging
from pathlib import Path
from typing import Optional

from pii_detector.config import MODEL_PATH, N_CTX, N_THREADS, TEMPERATURE, MAX_TOKENS, N_GPU_LAYERS

logger = logging.getLogger(__name__)


class QwenLLM:
    """Local Qwen 2.5 3B Instruct GGUF model wrapper using llama-cpp-python."""

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = Path(model_path) if model_path else MODEL_PATH
        self._model = None

    @property
    def model(self):
        if self._model is None:
            if not self.model_path.exists():
                raise FileNotFoundError(f"Local Qwen GGUF model file not found at: {self.model_path}")
            try:
                from llama_cpp import Llama
                logger.info(f"Loading local Qwen GGUF model from {self.model_path}")
                self._model = Llama(
                    model_path=str(self.model_path),
                    n_ctx=N_CTX,
                    n_threads=N_THREADS,
                    n_gpu_layers=N_GPU_LAYERS,
                    verbose=False
                )
            except Exception as e:
                logger.error(f"Error loading Qwen GGUF model: {e}")
                raise RuntimeError(f"Could not load local Qwen model: {e}") from e
        return self._model

    def generate(self, prompt: str, max_tokens: int = MAX_TOKENS, temperature: float = TEMPERATURE) -> str:
        formatted_prompt = f"<|im_start|>user\n{prompt}\n<|im_end|>\n<|im_start|>assistant\n"
        output = self.model(
            formatted_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=["<|im_end|>"]
        )
        return output["choices"][0]["text"].strip()
