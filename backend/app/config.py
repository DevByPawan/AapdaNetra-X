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
    db_echo: bool = False

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
