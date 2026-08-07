import sys
from pathlib import Path
from contextlib import asynccontextmanager

# Register sys.path and sys.modules alias
backend_dir = Path(__file__).resolve().parent.parent
agents_dir = backend_dir / "app" / "agents"

if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(agents_dir) not in sys.path:
    sys.path.insert(0, str(agents_dir))

try:
    import app.agents as pii_detector
    sys.modules["pii_detector"] = pii_detector
except Exception as e:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_db
from app.api.v1.router import api_v1_router
from app.agents.web.app import app as multi_agent_app

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables on startup
    await init_db()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Set CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include both PS_v5 API routes and PS_v3 Multi-Agent App routes
app.include_router(api_v1_router)
app.mount("/agent-engine", multi_agent_app)

# Include PS_v3 direct routes on main app
for route in multi_agent_app.routes:
    if hasattr(route, "path") and hasattr(route, "endpoint") and hasattr(route, "methods"):
        if route.path.startswith("/api/"):
            try:
                app.add_api_route(
                    path=route.path,
                    endpoint=route.endpoint,
                    methods=route.methods,
                    tags=["Multi-Agent Engine"]
                )
            except Exception:
                pass

@app.get("/")
async def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} Multi-Agent Privacy Engine",
        "version": settings.VERSION,
        "docs_url": "http://127.0.0.1:8000/docs",
        "api_v1": "http://127.0.0.1:8000/api/v1",
        "health": "http://127.0.0.1:8000/health"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION
    }
