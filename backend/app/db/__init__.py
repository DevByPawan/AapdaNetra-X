"""AapdaNetra-X Database Infrastructure — Phase 6.5A

Provides async PostgreSQL/PostGIS connectivity via SQLAlchemy 2.x.
Controlled by PERSISTENCE_MODE environment variable:
  - disabled:  no database initialization (default)
  - optional:  attempt connection, continue without on failure
  - required:  database must be available
"""

from app.db.session import (
    DatabaseManager,
    get_db_manager,
)

__all__ = [
    "DatabaseManager",
    "get_db_manager",
]
