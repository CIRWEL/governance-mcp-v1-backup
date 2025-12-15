"""
Consolidated Governance Database

Provides a single SQLite database file for all governance data, replacing
multiple separate database files with one unified store.

Architecture:
- Single governance.db file contains all tables
- Each module (metadata, state, calibration, etc.) uses this shared DB
- WAL mode for concurrent access across modules
- Unified schema versioning

Tables:
- agent_metadata (from metadata_db.py)
- agent_state (from state_db.py)
- calibration_state (from calibration_db.py)
- dialectic_sessions, dialectic_messages (from dialectic_db.py)
- discoveries, discovery_tags, discovery_edges (from knowledge_db.py)
- audit_events (from audit_db.py)
"""

import os
import sqlite3
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from src.logging_utils import get_logger

logger = get_logger(__name__)

# Single database path for all governance data
DEFAULT_DB_PATH = Path(
    os.getenv(
        "UNITARES_GOVERNANCE_DB_PATH",
        str(Path(__file__).parent.parent / "data" / "governance.db")
    )
)

# Global connection pool (one per thread/process)
_db_path: Optional[Path] = None


def get_db_path() -> Path:
    """Get the governance database path."""
    global _db_path
    if _db_path is None:
        _db_path = DEFAULT_DB_PATH
        _db_path.parent.mkdir(parents=True, exist_ok=True)
    return _db_path


def get_connection(timeout: float = 30.0) -> sqlite3.Connection:
    """
    Get a new database connection with standard settings.
    
    Each call returns a new connection (thread-safe pattern).
    Connections should be used with context manager or closed explicitly.
    """
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path), timeout=timeout)
    conn.row_factory = sqlite3.Row
    
    # Standard pragmas for all governance operations
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    
    return conn


@contextmanager
def connection_context(timeout: float = 30.0):
    """Context manager for database connections."""
    conn = get_connection(timeout)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema_versioning() -> None:
    """Initialize the unified schema versioning table."""
    with connection_context() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_versions (
                component TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)


def get_schema_version(component: str) -> int:
    """Get schema version for a component."""
    try:
        with connection_context() as conn:
            cursor = conn.execute(
                "SELECT version FROM schema_versions WHERE component = ?",
                (component,)
            )
            row = cursor.fetchone()
            return row['version'] if row else 0
    except sqlite3.OperationalError:
        return 0


def set_schema_version(component: str, version: int, conn: Optional[sqlite3.Connection] = None) -> None:
    """Set schema version for a component.
    
    Args:
        component: Component name
        version: Schema version number
        conn: Optional existing connection (to avoid opening new connection during migrations)
    """
    from datetime import datetime
    if conn is not None:
        # Use provided connection (for migrations)
        conn.execute("""
            INSERT OR REPLACE INTO schema_versions (component, version, updated_at)
            VALUES (?, ?, ?)
        """, (component, version, datetime.now().isoformat()))
        conn.commit()
    else:
        # Open new connection (for normal use)
        with connection_context() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO schema_versions (component, version, updated_at)
                VALUES (?, ?, ?)
            """, (component, version, datetime.now().isoformat()))


def migrate_from_legacy_dbs(data_dir: Path = None) -> dict:
    """
    Migrate data from legacy separate databases to consolidated governance.db.
    
    Returns migration statistics.
    """
    if data_dir is None:
        data_dir = Path(__file__).parent.parent / "data"
    
    stats = {
        "agent_metadata": 0,
        "agent_state": 0,
        "calibration": 0,
        "dialectic_sessions": 0,
        "dialectic_messages": 0,
        "discoveries": 0,
        "audit_events": 0,
        "errors": []
    }
    
    # Initialize schema versioning
    init_schema_versioning()
    
    # Migrate each legacy database
    legacy_dbs = [
        ("agent_metadata.db", "agent_metadata", _migrate_agent_metadata),
        ("agent_state.db", "agent_state", _migrate_agent_state),
        ("calibration.db", "calibration", _migrate_calibration),
        ("dialectic.db", "dialectic", _migrate_dialectic),
        ("knowledge.db", "knowledge", _migrate_knowledge),
        ("audit.db", "audit", _migrate_audit),
    ]
    
    for db_file, component, migrate_func in legacy_dbs:
        legacy_path = data_dir / db_file
        if legacy_path.exists():
            try:
                count = migrate_func(legacy_path)
                stats[component if component in stats else f"{component}_total"] = count
                logger.info(f"Migrated {count} records from {db_file}")
            except Exception as e:
                stats["errors"].append(f"{db_file}: {e}")
                logger.error(f"Failed to migrate {db_file}: {e}", exc_info=True)
    
    return stats


def _migrate_agent_metadata(legacy_path: Path) -> int:
    """Migrate agent_metadata table."""
    # Open legacy connection with timeout
    legacy_conn = sqlite3.connect(str(legacy_path), timeout=30.0)
    legacy_conn.row_factory = sqlite3.Row
    legacy_conn.execute("PRAGMA busy_timeout=30000")
    
    try:
        # Create table in governance.db
        with connection_context(timeout=60.0) as conn:  # Longer timeout for migrations
            # Get schema from legacy
            cursor = legacy_conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='agent_metadata'"
            )
            schema = cursor.fetchone()
            if schema:
                conn.execute(schema['sql'])
            
            # Copy data
            cursor = legacy_conn.execute("SELECT * FROM agent_metadata")
            rows = cursor.fetchall()
            
            for row in rows:
                placeholders = ", ".join(["?"] * len(row))
                columns = ", ".join(row.keys())
                conn.execute(
                    f"INSERT OR REPLACE INTO agent_metadata ({columns}) VALUES ({placeholders})",
                    tuple(row)
                )
            
            # Use existing connection instead of opening new one
            set_schema_version("agent_metadata", 1, conn=conn)
        
        return len(rows)
    finally:
        legacy_conn.close()


def _migrate_agent_state(legacy_path: Path) -> int:
    """Migrate agent_state table."""
    # Open legacy connection with timeout
    legacy_conn = sqlite3.connect(str(legacy_path), timeout=30.0)
    legacy_conn.row_factory = sqlite3.Row
    legacy_conn.execute("PRAGMA busy_timeout=30000")
    
    try:
        with connection_context(timeout=60.0) as conn:  # Longer timeout for migrations
            cursor = legacy_conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='agent_state'"
            )
            schema = cursor.fetchone()
            if schema:
                conn.execute(schema['sql'])
            
            cursor = legacy_conn.execute("SELECT * FROM agent_state")
            rows = cursor.fetchall()
            
            for row in rows:
                placeholders = ", ".join(["?"] * len(row))
                columns = ", ".join(row.keys())
                conn.execute(
                    f"INSERT OR REPLACE INTO agent_state ({columns}) VALUES ({placeholders})",
                    tuple(row)
                )
            
            # Copy indexes
            for idx in legacy_conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='agent_state' AND sql IS NOT NULL"
            ):
                try:
                    conn.execute(idx['sql'])
                except sqlite3.OperationalError:
                    pass  # Index already exists
            
            # Use existing connection instead of opening new one
            set_schema_version("agent_state", 1, conn=conn)
        
        return len(rows)
    finally:
        legacy_conn.close()


def _migrate_calibration(legacy_path: Path) -> int:
    """Migrate calibration_state table."""
    # Open legacy connection with timeout
    legacy_conn = sqlite3.connect(str(legacy_path), timeout=30.0)
    legacy_conn.row_factory = sqlite3.Row
    legacy_conn.execute("PRAGMA busy_timeout=30000")
    
    try:
        with connection_context(timeout=60.0) as conn:  # Longer timeout for migrations
            cursor = legacy_conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='calibration_state'"
            )
            schema = cursor.fetchone()
            if schema:
                conn.execute(schema['sql'])
            
            cursor = legacy_conn.execute("SELECT * FROM calibration_state")
            rows = cursor.fetchall()
            
            for row in rows:
                placeholders = ", ".join(["?"] * len(row))
                columns = ", ".join(row.keys())
                conn.execute(
                    f"INSERT OR REPLACE INTO calibration_state ({columns}) VALUES ({placeholders})",
                    tuple(row)
                )
            
            # Use existing connection instead of opening new one
            set_schema_version("calibration", 1, conn=conn)
        
        return len(rows)
    finally:
        legacy_conn.close()


def _migrate_dialectic(legacy_path: Path) -> int:
    """Migrate dialectic tables."""
    from datetime import datetime
    legacy_conn = sqlite3.connect(str(legacy_path), timeout=30.0)
    legacy_conn.row_factory = sqlite3.Row
    legacy_conn.execute("PRAGMA busy_timeout=30000")
    total = 0
    
    try:
        with connection_context(timeout=60.0) as conn:
            for table in ['dialectic_sessions', 'dialectic_messages']:
                cursor = legacy_conn.execute(
                    f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'"
                )
                schema = cursor.fetchone()
                if schema and schema['sql']:
                    conn.execute(schema['sql'])
                
                cursor = legacy_conn.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                
                for row in rows:
                    placeholders = ", ".join(["?"] * len(row))
                    columns = ", ".join(row.keys())
                    conn.execute(
                        f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({placeholders})",
                        tuple(row)
                    )
                
                total += len(rows)
            
            # Copy indexes
            for idx in legacy_conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
            ):
                if idx['sql']:
                    try:
                        conn.execute(idx['sql'])
                    except sqlite3.OperationalError:
                        pass
            
            conn.execute("""
                INSERT OR REPLACE INTO schema_versions (component, version, updated_at)
                VALUES (?, ?, ?)
            """, ("dialectic", 1, datetime.now().isoformat()))
    finally:
        legacy_conn.close()
    return total


def _migrate_knowledge(legacy_path: Path) -> int:
    """Migrate knowledge graph tables (excluding FTS - will be rebuilt)."""
    from datetime import datetime
    legacy_conn = sqlite3.connect(str(legacy_path), timeout=30.0)
    legacy_conn.row_factory = sqlite3.Row
    legacy_conn.execute("PRAGMA busy_timeout=30000")
    total = 0
    
    try:
        with connection_context(timeout=60.0) as conn:
            # Migrate main tables (FTS will be rebuilt by triggers)
            for table in ['discoveries', 'discovery_tags', 'discovery_edges', 'rate_limits']:
                try:
                    cursor = legacy_conn.execute(
                        f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'"
                    )
                    schema = cursor.fetchone()
                    if schema and schema['sql']:
                        conn.execute(schema['sql'])
                    
                    cursor = legacy_conn.execute(f"SELECT * FROM {table}")
                    rows = cursor.fetchall()
                    
                    for row in rows:
                        placeholders = ", ".join(["?"] * len(row))
                        columns = ", ".join(row.keys())
                        conn.execute(
                            f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({placeholders})",
                            tuple(row)
                        )
                    
                    total += len(rows)
                except sqlite3.OperationalError as e:
                    logger.debug(f"Table {table} migration: {e}")
            
            # Copy indexes
            for idx in legacy_conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL AND name NOT LIKE '%fts%'"
            ):
                if idx['sql']:
                    try:
                        conn.execute(idx['sql'])
                    except sqlite3.OperationalError:
                        pass
            
            conn.execute("""
                INSERT OR REPLACE INTO schema_versions (component, version, updated_at)
                VALUES (?, ?, ?)
            """, ("knowledge", 1, datetime.now().isoformat()))
    finally:
        legacy_conn.close()
    return total


def _migrate_audit(legacy_path: Path) -> int:
    """Migrate audit tables (excluding FTS - will be rebuilt)."""
    # Open legacy connection with timeout
    legacy_conn = sqlite3.connect(str(legacy_path), timeout=30.0)
    legacy_conn.row_factory = sqlite3.Row
    legacy_conn.execute("PRAGMA busy_timeout=30000")
    total = 0
    
    try:
        with connection_context(timeout=60.0) as conn:  # Longer timeout for migrations
            # Migrate main audit_events table
            cursor = legacy_conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='audit_events'"
            )
            schema = cursor.fetchone()
            if schema and schema['sql']:
                conn.execute(schema['sql'])
            
            cursor = legacy_conn.execute("SELECT * FROM audit_events")
            rows = cursor.fetchall()
            
            for row in rows:
                placeholders = ", ".join(["?"] * len(row))
                columns = ", ".join(row.keys())
                conn.execute(
                    f"INSERT OR REPLACE INTO audit_events ({columns}) VALUES ({placeholders})",
                    tuple(row)
                )
            
            total = len(rows)
            
            # Copy indexes
            for idx in legacy_conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL AND name NOT LIKE '%fts%'"
            ):
                if idx['sql']:
                    try:
                        conn.execute(idx['sql'])
                    except sqlite3.OperationalError:
                        pass
            
            from datetime import datetime
            conn.execute("""
                INSERT OR REPLACE INTO schema_versions (component, version, updated_at)
                VALUES (?, ?, ?)
            """, ("audit", 1, datetime.now().isoformat()))
    finally:
        legacy_conn.close()
    return total


def get_statistics() -> dict:
    """Get statistics about the consolidated database."""
    stats = {}
    
    try:
        with connection_context() as conn:
            # Count rows in each table
            tables = [
                'agent_metadata', 'agent_state', 'calibration_state',
                'dialectic_sessions', 'dialectic_messages',
                'discoveries', 'audit_events'
            ]
            
            for table in tables:
                try:
                    cursor = conn.execute(f"SELECT COUNT(*) as count FROM {table}")
                    stats[table] = cursor.fetchone()['count']
                except sqlite3.OperationalError:
                    stats[table] = 0
            
            # Database file size
            db_path = get_db_path()
            if db_path.exists():
                stats['file_size_bytes'] = db_path.stat().st_size
                stats['file_size_mb'] = round(stats['file_size_bytes'] / (1024 * 1024), 2)
            
            # Schema versions
            try:
                cursor = conn.execute("SELECT component, version FROM schema_versions")
                stats['schema_versions'] = {row['component']: row['version'] for row in cursor}
            except sqlite3.OperationalError:
                stats['schema_versions'] = {}
    
    except Exception as e:
        stats['error'] = str(e)
    
    return stats

