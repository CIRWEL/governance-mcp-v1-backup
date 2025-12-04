"""
Standardized logging utilities.

This module provides consistent logging patterns for the governance system.
Use this instead of print() statements for better log management.

Usage:
    from src.logging_utils import get_logger
    
    logger = get_logger(__name__)
    logger.info("Operation completed")
    logger.warning("Deprecated field used")
    logger.error("Operation failed", exc_info=True)
"""

import logging
import sys
from typing import Optional

# Configure root logger
_logger_configured = False


def configure_logging(level: int = logging.INFO, format_string: Optional[str] = None):
    """
    Configure root logger for the governance system.
    
    Args:
        level: Logging level (default: INFO)
        format_string: Custom format string (optional)
    """
    global _logger_configured
    
    if _logger_configured:
        return
    
    if format_string is None:
        format_string = "[UNITARES] %(name)s - %(levelname)s - %(message)s"
    
    logging.basicConfig(
        level=level,
        format=format_string,
        stream=sys.stderr,  # Log to stderr (MCP convention)
        force=True  # Override any existing configuration
    )
    
    _logger_configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.
    
    Args:
        name: Module name (typically __name__)
    
    Returns:
        Logger instance
    """
    configure_logging()  # Ensure logging is configured
    return logging.getLogger(name)


# Auto-configure on import
configure_logging()

