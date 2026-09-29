"""AapdaNetra-X FastAPI Backend — Entry Point"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import incident, risk, forecast, routes, alerts, simulation, response, explainability, events, history, analytics, decision, spatial

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("aapdanetra")


# ── Phase 6.5A: Application Lifespan ─────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown of the database layer."""
    # ── Startup ───────────────────────────────────────────────────────
    mode = settings.persistence_mode.lower()

    if mode == "disabled":
        logger.info("Persistence mode: disabled — skipping database initialization")
    else:
        from app.db.session import get_db_manager

        db = get_db_manager()
        url = settings.effective_database_url
        success = await db.initialize(
            database_url=url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_recycle=settings.db_pool_recycle,
            pool_pre_ping=settings.db_pool_pre_ping,
            connect_timeout=settings.db_connect_timeout,
            command_timeout=settings.db_command_timeout,
            echo=settings.db_echo,
        )

        if success:
            logger.info("Persistence mode: %s — database ready", mode)
        elif mode == "required":
            logger.error(
                "Persistence mode: required — database unavailable: %s",
                db.initialization_error,
            )
            # Do NOT crash — let /health surface the failure.
        else:
            # optional mode — log and continue
            logger.warning(
                "Persistence mode: optional — database unavailable, "
                "continuing with in-memory behavior: %s",
                db.initialization_error,
            )

    yield  # ── Application runs here ──

    # ── Shutdown ──────────────────────────────────────────────────────
    if mode != "disabled":
        from app.db.session import get_db_manager

        db = get_db_manager()
        await db.dispose()


# ── App ──────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AapdaNetra-X API",
    description="Emergency Intelligence Platform — Disaster Monitoring & Response",
    version=settings.api_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID", "Accept"],
)

# ── Request logging, correlation & security headers middleware ──────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    from app.correlation import set_request_id, generate_request_id

    req_id = request.headers.get("X-Request-ID") or generate_request_id()
    set_request_id(req_id)

    start = datetime.now(timezone.utc)
    try:
        response_obj = await call_next(request)
    except Exception as exc:
        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        logger.error(f"[{req_id}] {request.method} {request.url.path} 500 {duration:.1f}ms - Unhandled Exception: {exc}", exc_info=True)
        response_obj = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": req_id},
        )

    duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000

    # Security & Observability Headers
    response_obj.headers["X-Request-ID"] = req_id
    response_obj.headers["X-Content-Type-Options"] = "nosniff"
    response_obj.headers["X-Frame-Options"] = "DENY"
    response_obj.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response_obj.headers["X-XSS-Protection"] = "1; mode=block"

    logger.info(
        f"[{req_id}] {request.method} {request.url.path}  {response_obj.status_code}  {duration:.1f}ms"
    )
    return response_obj

# ── Routers ───────────────────────────────────────────────────────────────
from app.routers import spatial

prefix = "/api"
app.include_router(incident.router,       prefix=prefix, tags=["Incident"])
app.include_router(risk.router,           prefix=prefix, tags=["Risk"])
app.include_router(forecast.router,       prefix=prefix, tags=["Forecast"])
app.include_router(routes.router,         prefix=prefix, tags=["Routes"])
app.include_router(alerts.router,         prefix=prefix, tags=["Alerts"])
app.include_router(simulation.router,     prefix=prefix, tags=["Simulation"])
app.include_router(response.router,       prefix=prefix, tags=["Response"])
app.include_router(explainability.router, prefix=prefix, tags=["Explainability"])
app.include_router(events.router,         prefix=prefix, tags=["Events"])
app.include_router(history.router,        prefix=prefix, tags=["History"])
app.include_router(analytics.router,      prefix=prefix, tags=["Analytics"])
app.include_router(decision.router,       prefix=prefix, tags=["Decision Support"])
app.include_router(spatial.router,        prefix=prefix, tags=["Spatial Intelligence"])


# ── Health ────────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    try:
        from app.data.providers.data_adapter import get_data_adapter
        adapter = get_data_adapter()
        telemetry = adapter.get_telemetry_metadata()
    except Exception:
        telemetry = {"data_mode": settings.data_mode, "fallback_used": True, "providers": {}}

    # Phase 6.5A / 6.7D: persistence metadata & database health check (non-sensitive)
    from app.db.session import get_db_manager
    persistence = await get_db_manager().check_health(settings.persistence_mode)

    # Phase 6.8: SSE Broker stats
    from app.events.broker import get_event_broker
    sse_stats = get_event_broker().get_stats()

    # Required persistence unavailable → system is degraded, not operational
    mode = settings.persistence_mode.lower()
    if mode == "required" and not persistence.get("available", False):
        status = "degraded"
    else:
        status = "operational"

    # Phase 6.12: Model metadata
    try:
        from ml.inference import get_predictor
        predictor = get_predictor()
        model_info = {
            "model_version": predictor.model_version,
            "model_data_status": predictor.model_data_status,
        }
    except Exception:
        model_info = {"model_version": "unknown", "model_data_status": "unavailable"}

    return {
        "status": status,
        "version": settings.api_version,
        "simulated": settings.use_simulated_data,
        "data_mode": settings.data_mode,
        "model": model_info,
        "providers": telemetry.get("providers", {}),
        "telemetry": telemetry,
        "persistence": persistence,
        "sse": sse_stats,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Phase 6.12: Model Information Endpoint ────────────────────────────────
@app.get("/api/model-info", tags=["ML"])
async def model_info():
    """Returns model metadata, version, data status, and feature schema.
    Explicitly distinguishes between synthetic-trained and real-world models."""
    try:
        from ml.inference import get_predictor
        predictor = get_predictor()
        info = predictor.model_info
    except Exception:
        info = {
            "model_name": "GradientBoostingRegressor",
            "model_version": "unknown",
            "model_data_status": "unavailable",
            "disclaimer": "Model information unavailable.",
        }
    return info


@app.get("/", tags=["System"])
async def root():
    return {"message": "AapdaNetra-X API", "docs": "/docs"}
