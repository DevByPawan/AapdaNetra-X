from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    use_simulated_data: bool = True
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:4173"]
    log_level: str = "INFO"
    api_version: str = "0.1.0"

    # ── Phase 6.1: Data Provider Configuration ────────────────────────
    # data_mode: "simulated" (Phase 5D default) | "live" | "hybrid"
    data_mode: str = "simulated"

    # OpenWeatherMap API
    openweathermap_api_key: str = ""
    openweathermap_lat: float = 28.6448
    openweathermap_lon: float = 77.2167

    # Water level source: "simulated" | "manual" | "api"
    water_level_source: str = "simulated"

    # Cache TTL for weather and water level API responses (seconds)
    weather_cache_ttl: int = 300
    water_level_cache_ttl: int = 60
    cwc_station_id: str = "EXAMPLE-STN-YAMUNA-01"

    # Fallback to simulated defaults on provider failure
    enable_fallback: bool = True

    # ── Phase 6.4: Contextual Data Providers ───────────────────────────
    traffic_api_key: str = ""
    traffic_api_url: str = ""
    traffic_cache_ttl: int = 180

    population_dataset_path: str = ""
    population_cache_ttl: int = 86400

    infrastructure_dataset_path: str = ""
    infrastructure_cache_ttl: int = 86400

    # ── Phase 6.14: Advanced GIS / Spatial Risk Intelligence ──────────
    dem_enabled: bool = False
    dem_source: str = "unavailable"
    dem_data_path: str = ""
    dem_cache_ttl: int = 86400

    hazard_layer_enabled: bool = False
    hazard_dataset_path: str = ""
    hazard_cache_ttl: int = 86400

    spatial_hazard_weight: float = 0.35
    spatial_crs: str = "EPSG:4326"
    projected_crs: str = "EPSG:3857"

    # ── Phase 6.15: Intelligent Alert System Configuration ─────────────
    # Note: Thresholds are configurable demonstration thresholds for decision support.
    alert_risk_high_threshold: float = 70.0
    alert_risk_critical_threshold: float = 85.0
    alert_risk_escalation_rate: float = 10.0  # % increase rate
    alert_rainfall_intensity_threshold: float = 75.0  # mm/h
    alert_water_level_threshold: float = 5.0  # meters
    alert_water_level_trend_threshold: float = 0.3  # m/h
    alert_spatial_hazard_exposure_threshold: float = 0.25
    alert_route_safety_drop_threshold: float = 0.20
    alert_stale_telemetry_seconds: int = 600

    # ── Phase 6.2: OSM Routing Configuration ───────────────────────────
    # routing_mode: "simulated" (Phase 5D default) | "osm" | "auto"
    routing_mode: str = "simulated"
    osm_graphml_path: str = "backend/app/data/osm_cache/delhi_sector_b.graphml"
    osm_bbox_west: float = 77.1900
    osm_bbox_south: float = 28.6100
    osm_bbox_east: float = 77.2600
    osm_bbox_north: float = 28.6700

    # ── Phase 6.5A: PostgreSQL/PostGIS Foundation ──────────────────────
    # persistence_mode: "disabled" | "optional" | "required"
    #   disabled  — no DB initialization, existing in-memory behavior
    #   optional  — attempt DB connection, continue without on failure
    #   required  — DB must be available, startup reports failure clearly
    persistence_mode: str = "disabled"

    # PostgreSQL connection components (used to build DATABASE_URL if not set)
    postgres_server: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "aapdanetra"
    postgres_user: str = "aapdanetra"
    postgres_password: str = ""

    # Direct DATABASE_URL override (takes precedence over individual fields)
    database_url: Optional[str] = None

    # Connection pool tuning
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_pool_pre_ping: bool = True
    db_connect_timeout: int = 10
    db_command_timeout: int = 30
    db_echo: bool = False

    # ── Phase 6.32: Security & Production Hardening ─────────────────────
    environment: str = "development"  # "development" | "staging" | "production"
    auth_enabled: bool = False
    api_key: str = ""
    secret_key: str = "aapdanetra-dev-secret-change-in-production"
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60
    max_request_body_bytes: int = 1_048_576  # 1MB
    max_sse_subscriptions_per_ip: int = 10
    sse_auth_required: bool = False
    max_replay_events: int = 100

    @property
    def effective_database_url(self) -> str:
        """Build the async database URL from components or use the override.

        Returns the asyncpg-compatible connection string.
        Never call this when persistence_mode is 'disabled'.
        """
        if self.database_url:
            url = self.database_url
            # Ensure async driver prefix
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url

        return (
            f"postgresql+asyncpg://{self.postgres_user}"
            f":{self.postgres_password}"
            f"@{self.postgres_server}:{self.postgres_port}"
            f"/{self.postgres_db}"
        )

    def validate_production_security(self) -> None:
        """Validate production deployment settings and fail safely if mandatory security settings are missing."""
        if self.environment.lower() == "production":
            if not self.auth_enabled and not self.api_key:
                raise ValueError("Production deployment requires auth_enabled=True or non-empty api_key.")
            if self.secret_key == "aapdanetra-dev-secret-change-in-production":
                raise ValueError("Production deployment requires custom secret_key.")
            if "*" in self.cors_origins:
                raise ValueError("Production deployment cannot use wildcard '*' in cors_origins.")
            if self.persistence_mode == "required" and not self.database_url and not self.postgres_password:
                raise ValueError("Production persistence mode 'required' requires explicit database credentials or DATABASE_URL.")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
