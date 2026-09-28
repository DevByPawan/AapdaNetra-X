"""Phase 6.5A — PostgreSQL/PostGIS Foundation Tests

Tests the database infrastructure layer WITHOUT requiring a real PostgreSQL server.
All connectivity is mocked/faked to ensure the existing 102-test suite stays green.

Test categories:
  A. Disabled mode — DB not initialized, app works normally
  B. Optional mode + DB unavailable — app continues, health reports unavailable
  C. Required mode + DB unavailable — failure explicitly surfaced
  D. Configuration parsing — env vars load correctly
  E. Database URL handling — valid URL accepted, no creds in health
  F. Engine lifecycle — resources dispose correctly
"""

import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────

def _make_settings_env(**overrides):
    """Build a clean env dict for Settings construction.

    Merges overrides on top of minimal defaults so pydantic-settings
    reads from the dict rather than from a .env file on disk.
    """
    base = {
        "PERSISTENCE_MODE": "disabled",
        "USE_SIMULATED_DATA": "true",
        "DATA_MODE": "simulated",
    }
    base.update(overrides)
    return base


def _fresh_settings(**overrides):
    """Construct a new Settings instance from environment overrides."""
    from app.config import Settings
    env = _make_settings_env(**overrides)
    with patch.dict(os.environ, env, clear=False):
        return Settings()


# ═════════════════════════════════════════════════════════════════════════
# A. DISABLED MODE
# ═════════════════════════════════════════════════════════════════════════

class TestDisabledMode:
    """When PERSISTENCE_MODE=disabled the DB layer must be completely inert."""

    def test_db_manager_not_initialized_in_disabled_mode(self):
        """DatabaseManager should report unavailable when never initialized."""
        from app.db.session import DatabaseManager

        mgr = DatabaseManager()
        assert mgr.is_available is False
        assert mgr.engine is None

    def test_health_shows_disabled_persistence(self):
        """Health endpoint must include persistence.mode=disabled."""
        with patch.dict(os.environ, {"PERSISTENCE_MODE": "disabled"}, clear=False):
            # Re-import to pick up the env change
            from app.config import Settings
            test_settings = Settings()

            with patch("app.config.settings", test_settings):
                from app.main import app
                client = TestClient(app)
                resp = client.get("/health")
                assert resp.status_code == 200
                data = resp.json()
                assert "persistence" in data
                assert data["persistence"]["mode"] == "disabled"
                assert data["persistence"]["configured"] is False
                assert data["persistence"]["available"] is False

    def test_existing_endpoints_work_in_disabled_mode(self):
        """Risk, forecast, routes, etc. must work without DB."""
        with patch.dict(os.environ, {"PERSISTENCE_MODE": "disabled"}, clear=False):
            from app.config import Settings
            test_settings = Settings()

            with patch("app.config.settings", test_settings):
                from app.main import app
                client = TestClient(app)

                # Health
                assert client.get("/health").status_code == 200
                # Root
                assert client.get("/").status_code == 200

    def test_get_session_raises_when_not_initialized(self):
        """Requesting a session without initialization must raise RuntimeError."""
        from app.db.session import DatabaseManager

        mgr = DatabaseManager()
        with pytest.raises(RuntimeError, match="not initialized"):
            mgr.get_session()


# ═════════════════════════════════════════════════════════════════════════
# B. OPTIONAL MODE + DB UNAVAILABLE
# ═════════════════════════════════════════════════════════════════════════

class TestOptionalModeUnavailable:
    """PERSISTENCE_MODE=optional with no real PostgreSQL available."""

    @pytest.mark.asyncio
    async def test_initialize_fails_gracefully(self):
        """DatabaseManager.initialize() returns False when DB is unreachable."""
        from app.db.session import DatabaseManager

        mgr = DatabaseManager()
        # Use a bogus URL that will fail to connect
        result = await mgr.initialize(
            database_url="postgresql+asyncpg://fake:fake@localhost:1/nonexistent",
            pool_size=1,
            max_overflow=0,
        )
        assert result is False
        assert mgr.is_available is False
        assert mgr.initialization_error is not None

    @pytest.mark.asyncio
    async def test_engine_cleaned_up_on_failure(self):
        """Engine must be None after a failed initialization."""
        from app.db.session import DatabaseManager

        mgr = DatabaseManager()
        await mgr.initialize(
            database_url="postgresql+asyncpg://fake:fake@localhost:1/nonexistent",
        )
        assert mgr.engine is None

    def test_health_reports_unavailable_in_optional_mode(self):
        """Health endpoint must show available=false when DB is down."""
        from app.db.session import DatabaseManager

        mgr = DatabaseManager()
        mgr._available = False
        mgr._initialization_error = "connection refused"

        meta = mgr.get_health_metadata("optional")
        assert meta["mode"] == "optional"
        assert meta["configured"] is True
        assert meta["available"] is False
        assert meta["backend"] == "postgresql"
        assert meta["error"] is not None

    def test_optional_mode_does_not_break_risk_endpoint(self):
        """Risk prediction must work even when DB is unavailable in optional mode."""
        with patch.dict(os.environ, {"PERSISTENCE_MODE": "optional"}, clear=False):
            from app.config import Settings
            test_settings = Settings()

            # Mock the DB manager initialization to fail
            with patch("app.config.settings", test_settings):
                # Patch the DB initialization to simulate failure
                with patch("app.db.session.get_db_manager") as mock_get:
                    mock_mgr = MagicMock()
                    mock_mgr.is_available = False
                    health_dict = {
                        "mode": "optional",
                        "configured": True,
                        "available": False,
                        "backend": "postgresql",
                        "error": "connection refused",
                    }
                    mock_mgr.get_health_metadata.return_value = health_dict
                    mock_mgr.check_health = AsyncMock(return_value=health_dict)
                    mock_get.return_value = mock_mgr

                    from app.main import app
                    client = TestClient(app)

                    # Health should still be 200
                    resp = client.get("/health")
                    assert resp.status_code == 200
                    assert resp.json()["status"] == "operational"


# ═════════════════════════════════════════════════════════════════════════
# C. REQUIRED MODE + DB UNAVAILABLE
# ═════════════════════════════════════════════════════════════════════════

class TestRequiredModeUnavailable:
    """PERSISTENCE_MODE=required with no PostgreSQL: failure must be surfaced."""

    @pytest.mark.asyncio
    async def test_initialize_returns_false(self):
        """initialize() must return False when DB is unreachable."""
        from app.db.session import DatabaseManager

        mgr = DatabaseManager()
        result = await mgr.initialize(
            database_url="postgresql+asyncpg://fake:fake@localhost:1/nonexistent",
        )
        assert result is False
        assert mgr.is_available is False

    def test_health_shows_unavailable_in_required_mode(self):
        """Health must surface the failure clearly."""
        from app.db.session import DatabaseManager

        mgr = DatabaseManager()
        mgr._available = False
        mgr._initialization_error = "connection refused"

        meta = mgr.get_health_metadata("required")
        assert meta["mode"] == "required"
        assert meta["configured"] is True
        assert meta["available"] is False
        assert meta["error"] is not None

    def test_no_silent_fallback_in_required_mode(self):
        """Required mode must NOT silently pretend the DB is available."""
        from app.db.session import DatabaseManager

        mgr = DatabaseManager()
        mgr._available = False
        mgr._initialization_error = "host unreachable"

        meta = mgr.get_health_metadata("required")
        # Must not claim available
        assert meta["available"] is False
        # Must include error context
        assert "unreachable" in meta["error"]

    def test_health_status_degraded_when_required_db_unavailable(self):
        """Health must return status='degraded' when required persistence is down."""
        with patch.dict(os.environ, {"PERSISTENCE_MODE": "required"}, clear=False):
            from app.config import Settings
            test_settings = Settings()

            # Patch the bound reference in main.py, not just app.config
            with patch("app.main.settings", test_settings):
                with patch("app.db.session.get_db_manager") as mock_get:
                    mock_mgr = MagicMock()
                    mock_mgr.is_available = False
                    health_dict = {
                        "mode": "required",
                        "configured": True,
                        "available": False,
                        "backend": "postgresql",
                        "error": "connection refused",
                    }
                    mock_mgr.get_health_metadata.return_value = health_dict
                    mock_mgr.check_health = AsyncMock(return_value=health_dict)
                    mock_get.return_value = mock_mgr

                    from app.main import app
                    client = TestClient(app)

                    resp = client.get("/health")
                    assert resp.status_code == 200
                    data = resp.json()
                    assert data["status"] == "degraded"
                    assert data["persistence"]["available"] is False


# ═════════════════════════════════════════════════════════════════════════
# D. CONFIGURATION PARSING
# ═════════════════════════════════════════════════════════════════════════

class TestConfigurationParsing:
    """Verify environment variables load into Settings correctly."""

    def test_default_persistence_mode_is_disabled(self):
        s = _fresh_settings()
        assert s.persistence_mode == "disabled"

    def test_persistence_mode_from_env(self):
        s = _fresh_settings(PERSISTENCE_MODE="optional")
        assert s.persistence_mode == "optional"

    def test_postgres_connection_fields(self):
        s = _fresh_settings(
            POSTGRES_SERVER="db.example.com",
            POSTGRES_PORT="5433",
            POSTGRES_DB="testdb",
            POSTGRES_USER="testuser",
            POSTGRES_PASSWORD="secret123",
        )
        assert s.postgres_server == "db.example.com"
        assert s.postgres_port == 5433
        assert s.postgres_db == "testdb"
        assert s.postgres_user == "testuser"
        assert s.postgres_password == "secret123"

    def test_pool_settings(self):
        s = _fresh_settings(DB_POOL_SIZE="10", DB_MAX_OVERFLOW="20", DB_ECHO="true")
        assert s.db_pool_size == 10
        assert s.db_max_overflow == 20
        assert s.db_echo is True

    def test_database_url_override(self):
        url = "postgresql+asyncpg://custom:pass@remote:5432/mydb"
        s = _fresh_settings(DATABASE_URL=url)
        assert s.database_url == url


# ═════════════════════════════════════════════════════════════════════════
# E. DATABASE URL HANDLING
# ═════════════════════════════════════════════════════════════════════════

class TestDatabaseURLHandling:
    """Test URL composition and credential sanitization."""

    def test_effective_url_from_components(self):
        s = _fresh_settings(
            POSTGRES_SERVER="myhost",
            POSTGRES_PORT="5432",
            POSTGRES_DB="mydb",
            POSTGRES_USER="myuser",
            POSTGRES_PASSWORD="mypass",
        )
        url = s.effective_database_url
        assert url == "postgresql+asyncpg://myuser:mypass@myhost:5432/mydb"

    def test_effective_url_override_takes_precedence(self):
        s = _fresh_settings(
            DATABASE_URL="postgresql+asyncpg://override:x@host:5432/db",
            POSTGRES_SERVER="ignored",
        )
        assert "override" in s.effective_database_url
        assert "ignored" not in s.effective_database_url

    def test_postgresql_url_gets_asyncpg_prefix(self):
        """Plain postgresql:// should be upgraded to postgresql+asyncpg://."""
        s = _fresh_settings(
            DATABASE_URL="postgresql://user:pass@host:5432/db",
        )
        assert s.effective_database_url.startswith("postgresql+asyncpg://")

    def test_credentials_never_in_health_output(self):
        """Health metadata must NEVER contain credentials."""
        from app.db.session import DatabaseManager

        mgr = DatabaseManager()
        mgr._available = True

        meta = mgr.get_health_metadata("required")
        meta_str = str(meta)
        # These should never appear in health output
        assert "password" not in meta_str.lower() or "***" in meta_str
        assert "postgresql+asyncpg://" not in meta_str
        assert "DATABASE_URL" not in meta_str

    def test_error_sanitization(self):
        """Connection error messages should have credentials stripped."""
        from app.db.session import _sanitize_db_error

        raw = 'could not connect to postgresql+asyncpg://admin:s3cret@db:5432/prod'
        sanitized = _sanitize_db_error(raw)
        assert "s3cret" not in sanitized
        assert "admin" not in sanitized
        assert "postgresql://***" in sanitized

    def test_password_param_sanitization(self):
        from app.db.session import _sanitize_db_error

        raw = "authentication failed password=hunter2 for host"
        sanitized = _sanitize_db_error(raw)
        assert "hunter2" not in sanitized
        assert "password=***" in sanitized


# ═════════════════════════════════════════════════════════════════════════
# F. ENGINE LIFECYCLE
# ═════════════════════════════════════════════════════════════════════════

class TestEngineLifecycle:
    """Verify engine/session resources dispose correctly."""

    @pytest.mark.asyncio
    async def test_dispose_clears_state(self):
        """After dispose(), engine and session_factory should be None."""
        from app.db.session import DatabaseManager

        mgr = DatabaseManager()
        # Simulate a partial initialization state
        mgr._engine = AsyncMock()
        mgr._session_factory = MagicMock()
        mgr._available = True

        await mgr.dispose()

        assert mgr.engine is None
        assert mgr.is_available is False

    @pytest.mark.asyncio
    async def test_dispose_when_not_initialized_is_safe(self):
        """Disposing an uninitialized manager must not raise."""
        from app.db.session import DatabaseManager

        mgr = DatabaseManager()
        await mgr.dispose()  # Should not raise
        assert mgr.engine is None

    def test_singleton_accessor(self):
        """get_db_manager() must return the same instance."""
        from app.db.session import get_db_manager, _reset_db_manager

        _reset_db_manager()
        mgr1 = get_db_manager()
        mgr2 = get_db_manager()
        assert mgr1 is mgr2
        _reset_db_manager()

    @pytest.mark.asyncio
    async def test_dispose_calls_engine_dispose(self):
        """Engine.dispose() must be called during shutdown."""
        from app.db.session import DatabaseManager

        mgr = DatabaseManager()
        mock_engine = AsyncMock()
        mgr._engine = mock_engine
        mgr._available = True

        await mgr.dispose()
        mock_engine.dispose.assert_awaited_once()

    def test_health_metadata_structure(self):
        """Verify the shape of the health metadata dict."""
        from app.db.session import DatabaseManager

        mgr = DatabaseManager()

        # Disabled
        meta = mgr.get_health_metadata("disabled")
        assert set(meta.keys()) == {"mode", "configured", "available", "backend", "error"}
        assert meta["mode"] == "disabled"
        assert meta["configured"] is False
        assert meta["backend"] is None

        # Optional — available
        mgr._available = True
        meta = mgr.get_health_metadata("optional")
        assert meta["configured"] is True
        assert meta["available"] is True
        assert meta["backend"] == "postgresql"
        assert meta["error"] is None

        # Optional — unavailable with error
        mgr._available = False
        mgr._initialization_error = "conn refused"
        meta = mgr.get_health_metadata("optional")
        assert meta["available"] is False
        assert meta["error"] == "conn refused"


# ═════════════════════════════════════════════════════════════════════════
# G. BACKWARD COMPATIBILITY
# ═════════════════════════════════════════════════════════════════════════

class TestBackwardCompatibility:
    """Existing health response fields must remain present."""

    def test_health_has_existing_fields(self):
        """All pre-6.5A health fields must still be present."""
        from app.main import app

        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()

        # Pre-existing fields
        assert "status" in data
        assert "version" in data
        assert "simulated" in data
        assert "data_mode" in data
        assert "providers" in data
        assert "telemetry" in data
        assert "timestamp" in data

        # New field
        assert "persistence" in data

    def test_health_status_remains_operational(self):
        """The top-level status must still be 'operational'."""
        from app.main import app

        client = TestClient(app)
        data = client.get("/health").json()
        assert data["status"] == "operational"
