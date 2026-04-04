"""Grounded outcome-correlation study utilities.

The existing outcome table mixes exogenous results with endogenous
self-validation. This module explicitly separates them and refuses to return a
meaningful R^2 when the data cannot support one.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GroupKFold, cross_val_score


SNAPSHOT_FEATURES = [
    "eisv_e",
    "eisv_i",
    "eisv_s",
    "eisv_v",
    "eisv_phi",
    "eisv_coherence",
]


@dataclass
class DataQualityReport:
    total_outcomes: int
    endogenous_outcomes: int
    exogenous_outcomes: int
    exogenous_agents: int
    exogenous_negative_outcomes: int
    exogenous_any_snapshot: int
    exogenous_full_snapshot: int
    exogenous_score_std: float
    identity_join_agents: int
    state_join_agents: int
    audit_join_agents: int
    first_behavioral_timestamp: Optional[str]
    notes: list[str] = field(default_factory=list)


@dataclass
class RegressionReport:
    status: str
    sample_count: int
    agent_count: int
    feature_count: int
    folds: int
    r2_mean: Optional[float] = None
    r2_std: Optional[float] = None
    reason: Optional[str] = None


@dataclass
class GroundedOutcomeStudyReport:
    data_quality: DataQualityReport
    grounded_snapshot_regression: RegressionReport
    endogenous_snapshot_diagnostic: RegressionReport
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_detail(detail: Any) -> dict[str, Any]:
    """Parse JSON-ish detail payloads into a dict."""
    if detail is None:
        return {}
    if isinstance(detail, dict):
        return detail
    if isinstance(detail, str):
        try:
            parsed = json.loads(detail)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def classify_outcome_provenance(outcome_type: str, detail: Any) -> str:
    """Classify whether an outcome is exogenous enough for grounding."""
    parsed = parse_detail(detail)

    if outcome_type in {"trajectory_validated", "cirs_resonance"}:
        return "endogenous"

    if outcome_type in {"test_passed", "test_failed", "drawing_completed", "drawing_abandoned"}:
        return "exogenous"

    if outcome_type in {"task_completed", "task_failed"}:
        if parsed.get("source") == "auto_checkin":
            return "endogenous"
        if parsed.get("action"):
            return "exogenous"

    return "unknown"


def prepare_outcome_frame(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Normalize outcome rows for downstream analysis."""
    frame = outcomes.copy()
    if "detail" not in frame.columns:
        frame["detail"] = None

    frame["detail_parsed"] = frame["detail"].map(parse_detail)
    frame["provenance"] = [
        classify_outcome_provenance(ot, detail)
        for ot, detail in zip(frame["outcome_type"], frame["detail"])
    ]
    frame["has_any_snapshot"] = frame[SNAPSHOT_FEATURES].notna().any(axis=1)
    frame["has_full_snapshot"] = frame[SNAPSHOT_FEATURES].notna().all(axis=1)
    return frame


def compute_data_quality_report(
    outcomes: pd.DataFrame,
    *,
    identity_agent_ids: Iterable[str],
    state_agent_ids: Iterable[str],
    audit_agent_ids: Iterable[str],
    first_behavioral_timestamp: Optional[str],
) -> DataQualityReport:
    """Quantify whether the grounded study is feasible."""
    prepared = prepare_outcome_frame(outcomes)
    endogenous = prepared[prepared["provenance"] == "endogenous"]
    exogenous = prepared[prepared["provenance"] == "exogenous"]

    ex_agent_ids = set(exogenous["agent_id"].dropna().astype(str).unique())
    identity_agent_ids = set(identity_agent_ids)
    state_agent_ids = set(state_agent_ids)
    audit_agent_ids = set(audit_agent_ids)

    exogenous_score_std = 0.0
    if not exogenous.empty:
        exogenous_score_std = float(exogenous["outcome_score"].astype(float).std(ddof=0))
        if math.isnan(exogenous_score_std):
            exogenous_score_std = 0.0

    notes: list[str] = []
    if exogenous.empty:
        notes.append("No exogenous outcome labels were found.")
    if not exogenous.empty and exogenous["is_bad"].astype(bool).sum() == 0:
        notes.append("No exogenous negative outcomes were recorded.")
    if not exogenous.empty and exogenous_score_std < 1e-9:
        notes.append("Exogenous outcome scores have zero variance.")
    if not exogenous.empty and int(exogenous["has_any_snapshot"].sum()) == 0:
        notes.append("Exogenous outcomes are not paired with any EISV snapshot.")
    if ex_agent_ids and not (ex_agent_ids & state_agent_ids):
        notes.append("No exogenous outcome agent_ids join to persisted state history.")
    if ex_agent_ids and not (ex_agent_ids & audit_agent_ids):
        notes.append("No exogenous outcome agent_ids join to audit-event trajectories.")
    if ex_agent_ids and len(ex_agent_ids & identity_agent_ids) < len(ex_agent_ids):
        notes.append("Most exogenous outcome agent_ids do not resolve to core.identities.")

    return DataQualityReport(
        total_outcomes=int(len(prepared)),
        endogenous_outcomes=int(len(endogenous)),
        exogenous_outcomes=int(len(exogenous)),
        exogenous_agents=len(ex_agent_ids),
        exogenous_negative_outcomes=int(exogenous["is_bad"].astype(bool).sum()) if not exogenous.empty else 0,
        exogenous_any_snapshot=int(exogenous["has_any_snapshot"].sum()) if not exogenous.empty else 0,
        exogenous_full_snapshot=int(exogenous["has_full_snapshot"].sum()) if not exogenous.empty else 0,
        exogenous_score_std=round(exogenous_score_std, 6),
        identity_join_agents=len(ex_agent_ids & identity_agent_ids),
        state_join_agents=len(ex_agent_ids & state_agent_ids),
        audit_join_agents=len(ex_agent_ids & audit_agent_ids),
        first_behavioral_timestamp=first_behavioral_timestamp,
        notes=notes,
    )


def fit_grouped_linear_r2(
    frame: pd.DataFrame,
    *,
    features: list[str] | None = None,
    target: str = "outcome_score",
    group: str = "agent_id",
    min_samples: int = 30,
    min_agents: int = 5,
) -> RegressionReport:
    """Fit grouped linear regression and return cross-validated R^2."""
    features = features or list(SNAPSHOT_FEATURES)
    required = [*features, target, group]
    if frame.empty:
        return RegressionReport(
            status="insufficient_data",
            sample_count=0,
            agent_count=0,
            feature_count=len(features),
            folds=0,
            reason="no rows",
        )

    usable = frame.dropna(subset=required).copy()
    sample_count = int(len(usable))
    agent_count = int(usable[group].astype(str).nunique())
    if sample_count < min_samples:
        return RegressionReport(
            status="insufficient_data",
            sample_count=sample_count,
            agent_count=agent_count,
            feature_count=len(features),
            folds=0,
            reason=f"need at least {min_samples} samples",
        )
    if agent_count < min_agents:
        return RegressionReport(
            status="insufficient_data",
            sample_count=sample_count,
            agent_count=agent_count,
            feature_count=len(features),
            folds=0,
            reason=f"need at least {min_agents} agents",
        )

    y = usable[target].astype(float).to_numpy()
    if float(np.nanstd(y)) < 1e-12:
        return RegressionReport(
            status="insufficient_data",
            sample_count=sample_count,
            agent_count=agent_count,
            feature_count=len(features),
            folds=0,
            reason="target has zero variance",
        )

    X = usable[features].astype(float).to_numpy()
    groups = usable[group].astype(str).to_numpy()
    folds = min(5, agent_count)
    if folds < 2:
        return RegressionReport(
            status="insufficient_data",
            sample_count=sample_count,
            agent_count=agent_count,
            feature_count=len(features),
            folds=0,
            reason="need at least 2 groups",
        )

    model = LinearRegression()
    cv = GroupKFold(n_splits=folds)
    scores = cross_val_score(model, X, y, cv=cv, groups=groups, scoring="r2")
    valid_scores = [float(score) for score in scores if not math.isnan(float(score))]
    if not valid_scores:
        return RegressionReport(
            status="insufficient_data",
            sample_count=sample_count,
            agent_count=agent_count,
            feature_count=len(features),
            folds=folds,
            reason="all cross-validated R^2 scores were undefined",
        )

    return RegressionReport(
        status="ok",
        sample_count=sample_count,
        agent_count=agent_count,
        feature_count=len(features),
        folds=folds,
        r2_mean=float(np.mean(valid_scores)),
        r2_std=float(np.std(valid_scores)),
    )


def summarize_report(report: GroundedOutcomeStudyReport) -> str:
    """Condense the study into a readable verdict."""
    dq = report.data_quality
    grounded = report.grounded_snapshot_regression
    internal = report.endogenous_snapshot_diagnostic

    lines = [
        (
            f"Grounded outcomes: {dq.exogenous_outcomes} across {dq.exogenous_agents} agents; "
            f"{dq.exogenous_negative_outcomes} negatives; snapshot coverage "
            f"{dq.exogenous_any_snapshot}/{dq.exogenous_outcomes}."
        ),
        (
            f"Identity/state coverage for grounded agents: identities {dq.identity_join_agents}/{dq.exogenous_agents}, "
            f"state history {dq.state_join_agents}/{dq.exogenous_agents}, audit history {dq.audit_join_agents}/{dq.exogenous_agents}."
        ),
    ]

    if grounded.status == "ok" and grounded.r2_mean is not None:
        lines.append(f"Grounded snapshot regression R^2={grounded.r2_mean:.3f} (±{grounded.r2_std:.3f}).")
    else:
        lines.append(f"Grounded regression unavailable: {grounded.reason}.")

    if internal.status == "ok" and internal.r2_mean is not None:
        lines.append(
            f"Endogenous self-validation diagnostic R^2={internal.r2_mean:.3f} "
            f"(±{internal.r2_std:.3f}) on {internal.sample_count} samples."
        )
    else:
        lines.append(f"Endogenous diagnostic unavailable: {internal.reason}.")

    if dq.notes:
        lines.append("Data-quality flags: " + "; ".join(dq.notes))

    return "\n".join(lines)


def run_grounded_outcome_study(
    outcomes: pd.DataFrame,
    *,
    identity_agent_ids: Iterable[str],
    state_agent_ids: Iterable[str],
    audit_agent_ids: Iterable[str],
    first_behavioral_timestamp: Optional[str] = None,
) -> GroundedOutcomeStudyReport:
    """Run the grounded study plus a clearly-labeled endogenous diagnostic."""
    prepared = prepare_outcome_frame(outcomes)
    quality = compute_data_quality_report(
        prepared,
        identity_agent_ids=identity_agent_ids,
        state_agent_ids=state_agent_ids,
        audit_agent_ids=audit_agent_ids,
        first_behavioral_timestamp=first_behavioral_timestamp,
    )

    grounded_rows = prepared[
        (prepared["provenance"] == "exogenous") & prepared["has_full_snapshot"]
    ]
    grounded_snapshot_regression = fit_grouped_linear_r2(grounded_rows)

    endogenous_rows = prepared[
        (prepared["outcome_type"] == "trajectory_validated") & prepared["has_full_snapshot"]
    ]
    endogenous_snapshot_diagnostic = fit_grouped_linear_r2(
        endogenous_rows,
        min_samples=100,
        min_agents=5,
    )

    report = GroundedOutcomeStudyReport(
        data_quality=quality,
        grounded_snapshot_regression=grounded_snapshot_regression,
        endogenous_snapshot_diagnostic=endogenous_snapshot_diagnostic,
        summary="",
    )
    report.summary = summarize_report(report)
    return report
