from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Project root (pii-detector/)
BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[3]

import torch

# Hardware Acceleration / CUDA Configuration
CUDA_AVAILABLE = torch.cuda.is_available()
DEVICE = "cuda" if CUDA_AVAILABLE else "cpu"
N_GPU_LAYERS = -1 if CUDA_AVAILABLE else 0  # Offload all LLM layers to GPU if CUDA is available

# Check model paths in order of preference
INTERNAL_MODEL_PATH = Path(__file__).resolve().parent / "model_local" / "qwen2.5-3b-instruct-q4_k_m.gguf"
ROOT_MODEL_PATH = BASE_DIR / "models_local" / "qwen2.5-3b-instruct-q4_k_m.gguf"

if INTERNAL_MODEL_PATH.exists():
    MODEL_PATH = INTERNAL_MODEL_PATH
elif ROOT_MODEL_PATH.exists():
    MODEL_PATH = ROOT_MODEL_PATH
else:
    MODEL_PATH = INTERNAL_MODEL_PATH

N_CTX = 4096
N_THREADS = 8
TEMPERATURE = 0.1
MAX_TOKENS = 1024


import os
from urllib.parse import quote_plus

# Try loading .env file from project root if python-dotenv is installed
try:
    from dotenv import load_dotenv
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
except ImportError:
    # Manual simple .env parser fallback if python-dotenv is not installed
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())

POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "Bhanu@1729")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "privacyshield")

POSTGRES_URL = f"postgresql://{POSTGRES_USER}:{quote_plus(POSTGRES_PASSWORD)}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Configure current LangSmith variables and privacy-safe tracing defaults.
from app.agents.observability import configure_langsmith

configure_langsmith()



