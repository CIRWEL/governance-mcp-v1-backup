"""Calibration operations mixin for PostgresBackend."""

from __future__ import annotations

import json
from typing import Any, Dict

from src.logging_utils import get_logger

logger = get_logger(__name__)


class CalibrationMixin:
    """Calibration data operations."""

    async def get_calibration(self) -> Dict[str, Any]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data, updated_at, version FROM core.calibration WHERE id = TRUE"
            )
            if not row:
                return {}
            data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
            data["_updated_at"] = row["updated_at"].isoformat() if row["updated_at"] else None
            data["_version"] = row["version"]
            return data

    async def update_calibration(self, data: Dict[str, Any]) -> bool:
        clean_data = {k: v for k, v in data.items() if not k.startswith("_")}
        async with self.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE core.calibration
                SET data = $1::jsonb, updated_at = now(), version = version + 1
                WHERE id = TRUE
                """,
                json.dumps(clean_data),
            )
            return "UPDATE 1" in result
