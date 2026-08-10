"""Privacy-safe LangSmith observability helpers.

Tracing is optional and never prevents the application from starting. The
global configuration hides inputs and outputs so document contents, queries,
PII mappings, and model responses are not sent to LangSmith.
"""

import os
from pathlib import Path
from typing import Any, Callable, Dict


def configure_langsmith() -> None:
    """Load unified env values and enforce zero-payload tracing defaults."""
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    except ImportError:
        pass

    legacy_key = os.environ.get("LANGCHAIN_API_KEY")
    if legacy_key and not os.environ.get("LANGSMITH_API_KEY"):
        os.environ["LANGSMITH_API_KEY"] = legacy_key.strip('"').strip("'")

    aliases = {
        "LANGSMITH_TRACING": ("LANGCHAIN_TRACING_V2", "true"),
        "LANGSMITH_PROJECT": ("LANGCHAIN_PROJECT", "PrivacyShieldAI"),
        "LANGSMITH_ENDPOINT": ("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com"),
    }
    for current_name, (legacy_name, default) in aliases.items():
        value = os.environ.get(current_name) or os.environ.get(legacy_name) or default
        os.environ[current_name] = value.strip('"').strip("'")

    os.environ.setdefault("LANGSMITH_HIDE_INPUTS", "true")
    os.environ.setdefault("LANGSMITH_HIDE_OUTPUTS", "true")
    os.environ.setdefault("LANGSMITH_HIDE_METADATA", "false")


configure_langsmith()

try:
    from langsmith import traceable as _langsmith_traceable
except ImportError:
    _langsmith_traceable = None


def traceable(*args: Any, **kwargs: Any) -> Callable:
    """Return LangSmith's decorator, or a no-op when the SDK is unavailable."""
    if _langsmith_traceable is not None:
        return _langsmith_traceable(*args, **kwargs)

    def decorator(func: Callable) -> Callable:
        return func

    return decorator


def observability_status() -> Dict[str, Any]:
    """Return non-secret diagnostics suitable for a health endpoint."""
    key_present = bool(os.environ.get("LANGSMITH_API_KEY", "").strip())
    enabled = os.environ.get("LANGSMITH_TRACING", "false").lower() == "true"
    return {
        "provider": "LangSmith",
        "configured": key_present,
        "tracing_enabled": enabled and key_present,
        "project": os.environ.get("LANGSMITH_PROJECT", "PrivacyShieldAI"),
        "endpoint": os.environ.get("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
        "privacy": {
            "inputs_hidden": os.environ.get("LANGSMITH_HIDE_INPUTS", "true").lower() == "true",
            "outputs_hidden": os.environ.get("LANGSMITH_HIDE_OUTPUTS", "true").lower() == "true",
            "metadata_hidden": os.environ.get("LANGSMITH_HIDE_METADATA", "false").lower() == "true",
        },
    }
