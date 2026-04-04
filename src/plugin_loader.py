"""Plugin loader for governance-mcp.

Discovers plugins via Python entry_points (group: governance_mcp.plugins).
Each plugin exposes a register() callable that is invoked at startup.

Set UNITARES_DISABLE_PLUGINS=1 to skip all plugin loading.
"""

import os
from importlib.metadata import entry_points
from src.logging_utils import get_logger

logger = get_logger(__name__)

_loaded_plugins: list[str] = []


def load_plugins() -> list[str]:
    """Discover and load governance-mcp plugins. Returns list of loaded plugin names."""
    if os.environ.get("UNITARES_DISABLE_PLUGINS"):
        logger.info("[PLUGIN] Plugin loading disabled via UNITARES_DISABLE_PLUGINS")
        return []

    loaded = []
    for ep in entry_points(group="governance_mcp.plugins"):
        try:
            register_fn = ep.load()
            register_fn()
            loaded.append(ep.name)
            logger.info(f"[PLUGIN] Loaded: {ep.name}")
        except Exception as e:
            logger.warning(f"[PLUGIN] Failed to load {ep.name}: {e}")

    _loaded_plugins.extend(loaded)
    return loaded


def get_loaded_plugins() -> list[str]:
    """Return names of plugins loaded so far."""
    return list(_loaded_plugins)
