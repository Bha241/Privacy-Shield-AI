import uvicorn
import os
import sys
from pathlib import Path

# Add backend and agents directory to sys.path
backend_dir = Path(__file__).resolve().parent
agents_dir = backend_dir / "app" / "agents"

if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

if str(agents_dir) not in sys.path:
    sys.path.insert(0, str(agents_dir))

# Alias pii_detector to app.agents
try:
    import app.agents as pii_detector
    sys.modules["pii_detector"] = pii_detector
except Exception as e:
    print(f"Module alias warning: {e}")

if __name__ == "__main__":
    print("Starting PrivacyShieldAI Multi-Agent Enterprise Backend on http://0.0.0.0:8000 (127.0.0.1 / localhost) ...", flush=True)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
