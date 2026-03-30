"""Outcome Correlation Study — does EISV instability predict bad outcomes?

Joins EISV snapshots with outcome events to compute:
1. Verdict distribution: bad-outcome rate per verdict (safe/caution/high-risk)
2. Metric correlations: Pearson r between each EISV metric and outcome_score
3. Risk binning: bad-outcome rate per risk score range

Data source: audit.outcome_events table (EISV snapshot embedded at outcome time).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class CorrelationReport:
    """Result of an outcome correlation study."""
    total_outcomes: int
    good_outcomes: int
    bad_outcomes: int
    verdict_distribution: Dict[str, Dict[str, Any]]
    metric_correlations: Dict[str, Optional[float]]
    risk_bins: List[Dict[str, Any]]
    summary: str


def _pearson_r(xs: List[float], ys: List[float]) -> Optional[float]:
    """Pearson correlation coefficient. Returns None if insufficient data or zero variance."""
    n = len(xs)
    if n < 3 or len(ys) != n:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    denom = math.sqrt(var_x * var_y)
    if denom < 1e-12:
        return None
    return cov / denom


def compute_verdict_distribution(outcomes: List[Dict]) -> Dict[str, Dict[str, Any]]:
    """Group outcomes by eisv_verdict, compute bad-outcome rate per verdict."""
    buckets: Dict[str, List[Dict]] = {}
    for o in outcomes:
        v = o.get("eisv_verdict") or "unknown"
        buckets.setdefault(v, []).append(o)

    result = {}
    for verdict, items in sorted(buckets.items()):
        bad = sum(1 for i in items if i.get("is_bad"))
        scores = [i["outcome_score"] for i in items if i.get("outcome_score") is not None]
        result[verdict] = {
            "count": len(items),
            "bad_count": bad,
            "bad_rate": round(bad / len(items), 4) if items else 0,
            "avg_score": round(sum(scores) / len(scores), 4) if scores else None,
        }
    return result


def compute_metric_correlations(outcomes: List[Dict]) -> Dict[str, Optional[float]]:
    """Pearson r between each EISV metric and outcome_score."""
    metrics = ["eisv_e", "eisv_i", "eisv_s", "eisv_v", "eisv_phi", "eisv_coherence"]
    scores = [o["outcome_score"] for o in outcomes if o.get("outcome_score") is not None]

    result = {}
    for m in metrics:
        xs = []
        ys = []
        for o in outcomes:
            if o.get(m) is not None and o.get("outcome_score") is not None:
                xs.append(float(o[m]))
                ys.append(float(o["outcome_score"]))
        r = _pearson_r(xs, ys)
        label = m.replace("eisv_", "").upper()
        result[label] = round(r, 4) if r is not None else None
    return result


# Risk bin boundaries aligned with behavioral assessment thresholds
_RISK_BINS = [
    (0.0, 0.35, "healthy"),
    (0.35, 0.60, "moderate"),
    (0.60, 1.01, "critical"),
]


def compute_risk_bins(outcomes: List[Dict]) -> List[Dict[str, Any]]:
    """Bin outcomes by behavioral risk score and compute bad rate per bin.

    Falls back to ODE-derived risk from EISV metrics if behavioral risk
    is not available in the detail payload.
    """
    bins: List[List[Dict]] = [[] for _ in _RISK_BINS]

    for o in outcomes:
        # Try behavioral risk from detail first
        risk = None
        detail = o.get("detail") or {}
        if isinstance(detail, dict):
            beh = detail.get("behavioral_eisv") or {}
            risk = beh.get("risk")

        # Fallback: rough risk from EISV metrics
        if risk is None:
            e = o.get("eisv_e")
            i_val = o.get("eisv_i")
            s = o.get("eisv_s")
            if e is not None and i_val is not None and s is not None:
                # Simplified risk proxy: lower E/I and higher S → higher risk
                risk = max(0.0, min(1.0, 0.3 * (1 - e) + 0.3 * (1 - i_val) + 0.4 * s))

        if risk is None:
            continue

        for idx, (lo, hi, _label) in enumerate(_RISK_BINS):
            if lo <= risk < hi:
                bins[idx].append(o)
                break

    result = []
    for idx, (lo, hi, label) in enumerate(_RISK_BINS):
        items = bins[idx]
        bad = sum(1 for i in items if i.get("is_bad"))
        result.append({
            "range": f"{lo:.2f}-{hi:.2f}",
            "label": label,
            "count": len(items),
            "bad_count": bad,
            "bad_rate": round(bad / len(items), 4) if items else 0,
        })
    return result


def _build_summary(report: CorrelationReport) -> str:
    """Generate a human-readable summary of the correlation study."""
    lines = [f"Outcomes: {report.total_outcomes} ({report.good_outcomes} good, {report.bad_outcomes} bad)"]

    # Verdict distribution insight
    for v, d in report.verdict_distribution.items():
        if d["count"] >= 3:
            lines.append(f"  {v}: {d['count']} outcomes, {d['bad_rate']*100:.1f}% bad")

    # Strongest correlations
    best_pos = max(
        ((k, v) for k, v in report.metric_correlations.items() if v is not None),
        key=lambda x: abs(x[1]),
        default=None,
    )
    if best_pos:
        k, v = best_pos
        direction = "positively" if v > 0 else "negatively"
        lines.append(f"Strongest correlation: {k} ({direction}, r={v:.3f})")

    # Risk bin insight
    for b in report.risk_bins:
        if b["count"] >= 3:
            lines.append(f"  Risk {b['label']} ({b['range']}): {b['count']} outcomes, {b['bad_rate']*100:.1f}% bad")

    return "\n".join(lines)


class OutcomeCorrelation:
    """Correlate EISV state with outcome quality."""

    async def run(
        self,
        agent_id: Optional[str] = None,
        since_hours: float = 168.0,
    ) -> CorrelationReport:
        """Run the correlation study against the outcome_events table."""
        outcomes = await self._fetch_outcomes(agent_id, since_hours)

        good = sum(1 for o in outcomes if not o.get("is_bad"))
        bad = sum(1 for o in outcomes if o.get("is_bad"))

        verdict_dist = compute_verdict_distribution(outcomes)
        correlations = compute_metric_correlations(outcomes)
        risk_bins = compute_risk_bins(outcomes)

        report = CorrelationReport(
            total_outcomes=len(outcomes),
            good_outcomes=good,
            bad_outcomes=bad,
            verdict_distribution=verdict_dist,
            metric_correlations=correlations,
            risk_bins=risk_bins,
            summary="",
        )
        report.summary = _build_summary(report)
        return report

    async def _fetch_outcomes(
        self, agent_id: Optional[str], since_hours: float
    ) -> List[Dict]:
        """Fetch outcome events with EISV snapshots from DB."""
        from src.db import get_db
        db = get_db()
        async with db.acquire() as conn:
            if agent_id:
                rows = await conn.fetch(
                    """
                    SELECT outcome_type, is_bad, outcome_score,
                           eisv_e, eisv_i, eisv_s, eisv_v, eisv_phi,
                           eisv_verdict, eisv_coherence, eisv_regime,
                           detail, ts, agent_id
                    FROM audit.outcome_events
                    WHERE agent_id = $1
                      AND ts >= now() - make_interval(hours => $2)
                    ORDER BY ts DESC
                    """,
                    agent_id, since_hours,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT outcome_type, is_bad, outcome_score,
                           eisv_e, eisv_i, eisv_s, eisv_v, eisv_phi,
                           eisv_verdict, eisv_coherence, eisv_regime,
                           detail, ts, agent_id
                    FROM audit.outcome_events
                    WHERE ts >= now() - make_interval(hours => $2)
                    ORDER BY ts DESC
                    """,
                    since_hours,
                )
            results = []
            for row in rows:
                d = dict(row)
                # Parse detail JSON if it's a string
                if isinstance(d.get("detail"), str):
                    import json
                    try:
                        d["detail"] = json.loads(d["detail"])
                    except (json.JSONDecodeError, TypeError):
                        d["detail"] = {}
                results.append(d)
            return results
