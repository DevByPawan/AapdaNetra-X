"""AapdaNetra-X FastAPI Backend — Entry Point"""
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import incident, risk, forecast, routes, alerts, simulation, response, explainability

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("aapdanetra")

# ── App ──────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AapdaNetra-X API",
    description="Emergency Intelligence Platform — Disaster Monitoring & Response",
    version=settings.api_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ─────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request logging middleware ────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = datetime.now(timezone.utc)
    response_obj = await call_next(request)
    duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
    logger.info(f"{request.method} {request.url.path}  {response_obj.status_code}  {duration:.1f}ms")
    return response_obj

# ── Routers ───────────────────────────────────────────────────────────────
prefix = "/api"
app.include_router(incident.router,       prefix=prefix, tags=["Incident"])
app.include_router(risk.router,           prefix=prefix, tags=["Risk"])
app.include_router(forecast.router,       prefix=prefix, tags=["Forecast"])
app.include_router(routes.router,         prefix=prefix, tags=["Routes"])
app.include_router(alerts.router,         prefix=prefix, tags=["Alerts"])
app.include_router(simulation.router,     prefix=prefix, tags=["Simulation"])
app.include_router(response.router,       prefix=prefix, tags=["Response"])
app.include_router(explainability.router, prefix=prefix, tags=["Explainability"])

# ── Health ────────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    return {
        "status": "operational",
        "version": settings.api_version,
        "simulated": settings.use_simulated_data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/", tags=["System"])
async def root():
    return {"message": "AapdaNetra-X API", "docs": "/docs"}
