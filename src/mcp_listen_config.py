"""
Default bind address and MCP transport-security allowlists.

Security defaults:
- Listen on 127.0.0.1 unless UNITARES_BIND_ALL_INTERFACES is set (opt-in 0.0.0.0).
- allowed_hosts / allowed_origins: localhost always; extras via env (no hardcoded LAN IPs in code).

See CLAUDE.md for environment variables.
"""

from __future__ import annotations

import os
from typing import List

from mcp.server.transport_security import TransportSecuritySettings


def env_truthy(name: str, default: bool = False) -> bool:
    """True if env var is 1/true/yes/on (case-insensitive)."""
    v = os.environ.get(name, "")
    if not v:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def split_csv_env(name: str) -> List[str]:
    """Split a comma-separated env var into stripped non-empty tokens."""
    raw = os.environ.get(name, "")
    return [x.strip() for x in raw.split(",") if x.strip()]


def default_listen_host() -> str:
    """
    Return the default socket bind address.

    127.0.0.1 unless UNITARES_BIND_ALL_INTERFACES is truthy (then 0.0.0.0).
    Override entirely with UNITARES_MCP_HOST if set (e.g. a specific LAN IP).
    """
    explicit = os.environ.get("UNITARES_MCP_HOST", "").strip()
    if explicit:
        return explicit
    if env_truthy("UNITARES_BIND_ALL_INTERFACES"):
        return "0.0.0.0"
    return "127.0.0.1"


def build_transport_security_settings() -> TransportSecuritySettings:
    """
    Build TransportSecuritySettings for FastMCP.

    Base allowlists always include localhost. Append UNITARES_MCP_ALLOWED_HOSTS and
    UNITARES_MCP_ALLOWED_ORIGINS (comma-separated). Optional opaque 'null' origin
    for file:// clients when UNITARES_MCP_ALLOW_NULL_ORIGIN is truthy (default true).
    """
    base_hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    extra_hosts = split_csv_env("UNITARES_MCP_ALLOWED_HOSTS")
    allowed_hosts = base_hosts + extra_hosts

    base_origins = [
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
    ]
    extra_origins = split_csv_env("UNITARES_MCP_ALLOWED_ORIGINS")
    allowed_origins = base_origins + extra_origins
    if env_truthy("UNITARES_MCP_ALLOW_NULL_ORIGIN", default=True):
        allowed_origins.append("null")

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


def cors_extra_origins() -> List[str]:
    """Optional extra CORS origins from UNITARES_HTTP_CORS_EXTRA_ORIGINS (comma-separated)."""
    return split_csv_env("UNITARES_HTTP_CORS_EXTRA_ORIGINS")
