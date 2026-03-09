"""
UNITARES Governance Exception Hierarchy

Typed exceptions for governance-mcp-v1. Use specific subtypes instead of
bare ``except Exception`` where the failure mode is known.
"""


class GovernanceError(Exception):
    """Base exception for all governance errors."""


# ── Database ──────────────────────────────────────────────────────────────

class DatabaseError(GovernanceError):
    """Base for database-related errors."""


class ConnectionError(DatabaseError):
    """Failed to connect or lost connection to the database."""


class QueryError(DatabaseError):
    """A query failed (syntax error, constraint violation, etc.)."""


class PoolExhaustedError(DatabaseError):
    """Connection pool has no available connections."""


# ── Identity ──────────────────────────────────────────────────────────────

class IdentityError(GovernanceError):
    """Base for identity/session errors."""


class IdentityNotFoundError(IdentityError):
    """Requested identity does not exist."""


class IdentityConflictError(IdentityError):
    """Identity operation conflicts with existing state (duplicate, etc.)."""


class SessionExpiredError(IdentityError):
    """Session has expired or is inactive."""


# ── Dialectic ─────────────────────────────────────────────────────────────

class DialecticError(GovernanceError):
    """Base for dialectic protocol errors."""


class SessionNotFoundError(DialecticError):
    """Dialectic session does not exist."""


class PhaseError(DialecticError):
    """Invalid phase transition in dialectic session."""


class ReviewerUnavailableError(DialecticError):
    """No reviewer available for the dialectic session."""


# ── Knowledge Graph ───────────────────────────────────────────────────────

class KnowledgeGraphError(GovernanceError):
    """Base for knowledge graph errors."""


class DiscoveryNotFoundError(KnowledgeGraphError):
    """Requested discovery does not exist."""


class DuplicateDiscoveryError(KnowledgeGraphError):
    """Discovery with this ID already exists."""


# ── Validation ────────────────────────────────────────────────────────────

class ValidationError(GovernanceError):
    """Base for input validation errors."""


class ParameterError(ValidationError):
    """Invalid or missing parameter."""


class RateLimitError(ValidationError):
    """Rate limit exceeded."""


# ── Governance State ──────────────────────────────────────────────────────

class GovernanceStateError(GovernanceError):
    """Base for EISV / governance state errors."""


class CoherenceError(GovernanceStateError):
    """Coherence check failed or is out of expected range."""


class VoidStateError(GovernanceStateError):
    """Void dimension is in an invalid or dangerous state."""
