"""
Enrichment Pipeline — self-registering decorator + async runner.

Usage:
    from .pipeline import enrichment, run_enrichment_pipeline

    @enrichment(order=10)
    def enrich_foo(ctx): ...

    @enrichment(order=20)
    async def enrich_bar(ctx): ...

    await run_enrichment_pipeline(ctx)
"""

import inspect
from typing import Callable, List, NamedTuple

from src.logging_utils import get_logger

logger = get_logger(__name__)


class _EnrichmentEntry(NamedTuple):
    fn: Callable
    order: int
    name: str
    is_async: bool


_ENRICHMENTS: List[_EnrichmentEntry] = []


def enrichment(order: int):
    """Register a function in the enrichment pipeline at *order*."""
    def decorator(fn: Callable) -> Callable:
        _ENRICHMENTS.append(_EnrichmentEntry(
            fn=fn,
            order=order,
            name=fn.__name__,
            is_async=inspect.iscoroutinefunction(fn),
        ))
        _ENRICHMENTS.sort(key=lambda e: e.order)
        return fn
    return decorator


async def run_enrichment_pipeline(ctx) -> None:
    """Run every registered enrichment in order. Each is fail-safe."""
    for entry in _ENRICHMENTS:
        try:
            if entry.is_async:
                await entry.fn(ctx)
            else:
                entry.fn(ctx)
        except Exception as exc:
            logger.debug(f"Enrichment {entry.name} failed: {exc}")


def get_enrichment_count() -> int:
    return len(_ENRICHMENTS)


def get_enrichment_names() -> List[str]:
    return [e.name for e in _ENRICHMENTS]
