#!/usr/bin/env python3
"""
Drift Analysis Script - Trajectory Validation & Ethical Drift Analysis

Analyzes trajectory self-validation data from PostgreSQL (primary) or
legacy JSONL telemetry (backward compat).

METRICS (PostgreSQL mode):
1. Convergence: Is norm_delta trending positive over time?
2. Decision correlation: Do proceed verdicts lead to better trajectory quality?
3. Verdict validation rate: What % of verdicts produce quality > 0.5?
4. EISV correlation: Which EISV components correlate with trajectory quality?

USAGE:
    python3 scripts/analysis/analyze_drift.py [--report] [--export-csv]
    python3 scripts/analysis/analyze_drift.py --source jsonl  # legacy mode
    python3 scripts/analysis/analyze_drift.py --agent AGENT_ID
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

async def load_from_postgres(
    agent_id: Optional[str] = None,
    db_url: str = "postgresql://postgres:postgres@localhost:5432/governance",
) -> List[Dict]:
    """Load trajectory validation events from PostgreSQL."""
    import asyncpg

    conn = await asyncpg.connect(db_url)
    try:
        query = """
            SELECT ts, agent_id, outcome_score AS trajectory_quality,
                   detail->>'prev_verdict' AS prev_verdict,
                   (detail->>'prev_norm')::float AS prev_norm,
                   (detail->>'current_norm')::float AS current_norm,
                   (detail->>'norm_delta')::float AS norm_delta,
                   eisv_e, eisv_i, eisv_s, eisv_v,
                   eisv_coherence, eisv_verdict
            FROM audit.outcome_events
            WHERE outcome_type = 'trajectory_validated'
        """
        params = []
        if agent_id:
            query += " AND agent_id = $1"
            params.append(agent_id)
        query += " ORDER BY ts"

        rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


def load_from_jsonl(
    telemetry_file: Path,
    agent_id: Optional[str] = None,
) -> List[Dict]:
    """Load drift telemetry from JSONL file (legacy)."""
    if not telemetry_file.exists():
        return []

    samples = []
    with open(telemetry_file, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                sample = json.loads(line)
                if agent_id is None or sample.get('agent_id') == agent_id:
                    samples.append(sample)
            except json.JSONDecodeError:
                continue
    return samples


# ---------------------------------------------------------------------------
# Statistics (PostgreSQL mode — trajectory validation)
# ---------------------------------------------------------------------------

def safe_mean(lst):
    return sum(lst) / len(lst) if lst else 0.0


def safe_std(lst):
    if len(lst) < 2:
        return 0.0
    mean = safe_mean(lst)
    return (sum((x - mean) ** 2 for x in lst) / len(lst)) ** 0.5


def compute_pg_statistics(rows: List[Dict]) -> Dict[str, Any]:
    """Compute statistics from trajectory_validated PostgreSQL rows."""
    if not rows:
        return {'error': 'No data'}

    qualities = [r['trajectory_quality'] for r in rows if r['trajectory_quality'] is not None]
    norm_deltas = [r['norm_delta'] for r in rows if r['norm_delta'] is not None]
    current_norms = [r['current_norm'] for r in rows if r['current_norm'] is not None]

    agents = list(set(r['agent_id'] for r in rows))
    timestamps = [r['ts'] for r in rows]

    # --- Convergence: is norm_delta trending positive? ---
    mid = len(norm_deltas) // 2
    first_deltas = norm_deltas[:mid] if mid > 0 else []
    second_deltas = norm_deltas[mid:] if mid > 0 else []
    convergence = None
    if first_deltas and second_deltas:
        first_mean = safe_mean(first_deltas)
        second_mean = safe_mean(second_deltas)
        convergence = {
            'improving': second_mean > first_mean,
            'first_half_mean_delta': first_mean,
            'second_half_mean_delta': second_mean,
            'delta_trend': second_mean - first_mean,
        }

    # --- Norm convergence (traditional) ---
    norm_convergence = None
    if current_norms and len(current_norms) >= 10:
        nm = len(current_norms) // 2
        first_norm = safe_mean(current_norms[:nm])
        second_norm = safe_mean(current_norms[nm:])
        if first_norm > 0.001:
            change_pct = (second_norm - first_norm) / first_norm * 100
            norm_convergence = {
                'improving': second_norm < first_norm,
                'first_half_mean': first_norm,
                'second_half_mean': second_norm,
                'change_pct': change_pct,
            }

    # --- Decision correlation: proceed vs pause quality ---
    proceed_q = [r['trajectory_quality'] for r in rows
                 if r.get('prev_verdict') == 'proceed' and r['trajectory_quality'] is not None]
    pause_q = [r['trajectory_quality'] for r in rows
               if r.get('prev_verdict') == 'pause' and r['trajectory_quality'] is not None]
    guide_q = [r['trajectory_quality'] for r in rows
               if r.get('prev_verdict') == 'guide' and r['trajectory_quality'] is not None]

    decision_correlation = {
        'proceed': {'count': len(proceed_q), 'mean_quality': safe_mean(proceed_q)},
        'pause': {'count': len(pause_q), 'mean_quality': safe_mean(pause_q)},
        'guide': {'count': len(guide_q), 'mean_quality': safe_mean(guide_q)},
    }

    # --- Verdict validation rate ---
    validated = sum(1 for q in qualities if q > 0.5)
    validation_rate = validated / len(qualities) if qualities else 0.0

    # --- EISV correlation with trajectory quality ---
    eisv_corr = {}
    for dim in ['eisv_e', 'eisv_i', 'eisv_s', 'eisv_v', 'eisv_coherence']:
        pairs = [(r[dim], r['trajectory_quality'])
                 for r in rows
                 if r.get(dim) is not None and r.get('trajectory_quality') is not None]
        if len(pairs) >= 10:
            xs, ys = zip(*pairs)
            eisv_corr[dim] = _pearson(list(xs), list(ys))

    return {
        'source': 'postgresql',
        'total_samples': len(rows),
        'agents': agents,
        'agent_count': len(agents),
        'time_range': {
            'start': str(min(timestamps)) if timestamps else None,
            'end': str(max(timestamps)) if timestamps else None,
        },
        'trajectory_quality': {
            'mean': safe_mean(qualities),
            'std': safe_std(qualities),
            'min': min(qualities) if qualities else 0.0,
            'max': max(qualities) if qualities else 0.0,
        },
        'norm_delta': {
            'mean': safe_mean(norm_deltas),
            'std': safe_std(norm_deltas),
            'positive_pct': sum(1 for d in norm_deltas if d > 0) / len(norm_deltas) * 100 if norm_deltas else 0,
        },
        'current_norm': {
            'mean': safe_mean(current_norms),
            'std': safe_std(current_norms),
        },
        'convergence': convergence,
        'norm_convergence': norm_convergence,
        'decision_correlation': decision_correlation,
        'verdict_validation_rate': validation_rate,
        'eisv_correlation': eisv_corr,
    }


def _pearson(xs: list, ys: list) -> float:
    """Pearson correlation coefficient."""
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = safe_mean(xs), safe_mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = (sum((x - mx) ** 2 for x in xs)) ** 0.5
    dy = (sum((y - my) ** 2 for y in ys)) ** 0.5
    if dx * dy == 0:
        return 0.0
    return num / (dx * dy)


# ---------------------------------------------------------------------------
# Statistics (JSONL legacy mode)
# ---------------------------------------------------------------------------

def compute_jsonl_statistics(samples: List[Dict]) -> Dict[str, Any]:
    """Compute statistics from legacy JSONL drift telemetry."""
    if not samples:
        return {'error': 'No samples'}

    norms = [s['norm'] for s in samples]
    cal_devs = [s['calibration_deviation'] for s in samples]
    cpx_divs = [s['complexity_divergence'] for s in samples]
    coh_devs = [s['coherence_deviation'] for s in samples]
    stab_devs = [s['stability_deviation'] for s in samples]

    agents = list(set(s['agent_id'] for s in samples))
    timestamps = [s['timestamp'] for s in samples]

    mid = len(norms) // 2
    first_half = safe_mean(norms[:mid]) if mid > 0 else None
    second_half = safe_mean(norms[mid:]) if mid > 0 else None

    convergence = None
    if first_half is not None and second_half is not None:
        change_pct = (second_half - first_half) / max(first_half, 0.001) * 100
        convergence = {
            'improving': second_half < first_half,
            'first_half_mean': first_half,
            'second_half_mean': second_half,
            'change_pct': change_pct,
        }

    proceed_norms = [s['norm'] for s in samples if s.get('decision') == 'proceed']
    pause_norms = [s['norm'] for s in samples if s.get('decision') == 'pause']

    return {
        'source': 'jsonl',
        'total_samples': len(samples),
        'agents': agents,
        'agent_count': len(agents),
        'time_range': {
            'start': min(timestamps) if timestamps else None,
            'end': max(timestamps) if timestamps else None,
        },
        'norm': {
            'mean': safe_mean(norms),
            'std': safe_std(norms),
            'min': min(norms) if norms else 0.0,
            'max': max(norms) if norms else 0.0,
        },
        'components': {
            'calibration_deviation': {'mean': safe_mean(cal_devs), 'std': safe_std(cal_devs)},
            'complexity_divergence': {'mean': safe_mean(cpx_divs), 'std': safe_std(cpx_divs)},
            'coherence_deviation': {'mean': safe_mean(coh_devs), 'std': safe_std(coh_devs)},
            'stability_deviation': {'mean': safe_mean(stab_devs), 'std': safe_std(stab_devs)},
        },
        'convergence': convergence,
        'decision_correlation': {
            'proceed': {'count': len(proceed_norms), 'mean_norm': safe_mean(proceed_norms)},
            'pause': {'count': len(pause_norms), 'mean_norm': safe_mean(pause_norms)},
        },
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_pg_report(stats: Dict[str, Any], agent_id: Optional[str] = None) -> str:
    """Generate markdown report from PostgreSQL trajectory data."""
    lines = [
        "# Trajectory Validation Analysis Report",
        "",
        f"**Generated:** {datetime.now().isoformat()}",
        f"**Data Source:** PostgreSQL (`audit.outcome_events`)",
        f"**Agent Filter:** {agent_id or 'All agents'}",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"- **Total Validation Events:** {stats['total_samples']}",
        f"- **Agents:** {stats['agent_count']}",
        f"- **Time Range:** {stats['time_range'].get('start', 'N/A')} to {stats['time_range'].get('end', 'N/A')}",
        "",
        "## Trajectory Quality",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Mean Quality | {stats['trajectory_quality']['mean']:.4f} |",
        f"| Std Dev | {stats['trajectory_quality']['std']:.4f} |",
        f"| Range | [{stats['trajectory_quality']['min']:.4f}, {stats['trajectory_quality']['max']:.4f}] |",
        f"| Validation Rate | {stats['verdict_validation_rate']:.1%} |",
        "",
        "## Norm Delta (improvement signal)",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Mean Δ | {stats['norm_delta']['mean']:.6f} |",
        f"| Std Dev | {stats['norm_delta']['std']:.6f} |",
        f"| Positive % | {stats['norm_delta']['positive_pct']:.1f}% |",
        "",
    ]

    # Convergence
    lines.extend(["## Convergence Analysis", ""])
    conv = stats.get('convergence')
    if conv:
        status = "IMPROVING" if conv['improving'] else "NOT IMPROVING"
        icon = "+" if conv['improving'] else "-"
        lines.extend([
            f"**Norm Delta Trend:** {icon} {status}",
            "",
            f"- First half mean delta: {conv['first_half_mean_delta']:.6f}",
            f"- Second half mean delta: {conv['second_half_mean_delta']:.6f}",
            f"- Delta trend: {conv['delta_trend']:+.6f}",
            "",
        ])

    nc = stats.get('norm_convergence')
    if nc:
        status = "CONVERGING" if nc['improving'] else "NOT CONVERGING"
        icon = "+" if nc['improving'] else "-"
        lines.extend([
            f"**Drift Norm Trend:** {icon} {status}",
            "",
            f"- First half mean norm: {nc['first_half_mean']:.4f}",
            f"- Second half mean norm: {nc['second_half_mean']:.4f}",
            f"- Change: {nc['change_pct']:+.1f}%",
            "",
        ])

    # Decision correlation
    lines.extend(["## Decision Correlation", ""])
    dc = stats['decision_correlation']
    lines.extend([
        "| Verdict | Count | Mean Quality |",
        "|---------|-------|--------------|",
    ])
    for verdict in ('proceed', 'pause', 'guide'):
        d = dc.get(verdict, {})
        if d.get('count', 0) > 0:
            lines.append(f"| {verdict} | {d['count']} | {d['mean_quality']:.4f} |")
    lines.append("")

    # EISV correlation
    eisv = stats.get('eisv_correlation', {})
    if eisv:
        lines.extend([
            "## EISV Correlation with Trajectory Quality",
            "",
            "| Dimension | Pearson r |",
            "|-----------|-----------|",
        ])
        for dim, r in sorted(eisv.items(), key=lambda x: abs(x[1]), reverse=True):
            label = dim.replace('eisv_', '').upper()
            lines.append(f"| {label} | {r:+.4f} |")
        lines.append("")

    lines.extend([
        "---",
        "",
        "*Generated from continuous trajectory self-validation data.*",
    ])
    return "\n".join(lines)


def generate_jsonl_report(stats: Dict[str, Any], agent_id: Optional[str] = None) -> str:
    """Generate markdown report from legacy JSONL data."""
    lines = [
        "# Ethical Drift Analysis Report (Legacy JSONL)",
        "",
        f"**Generated:** {datetime.now().isoformat()}",
        f"**Data Source:** drift_telemetry.jsonl",
        f"**Agent Filter:** {agent_id or 'All agents'}",
        "",
        "---",
        "",
        "## Summary Statistics",
        "",
        f"- **Total Samples:** {stats['total_samples']}",
        f"- **Agents:** {stats['agent_count']}",
        f"- **Time Range:** {stats['time_range'].get('start', 'N/A')} to {stats['time_range'].get('end', 'N/A')}",
        "",
        "## Drift Norm",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Mean | {stats['norm']['mean']:.4f} |",
        f"| Std Dev | {stats['norm']['std']:.4f} |",
        f"| Min | {stats['norm']['min']:.4f} |",
        f"| Max | {stats['norm']['max']:.4f} |",
        "",
        "## Component Analysis",
        "",
        "| Component | Mean | Std Dev |",
        "|-----------|------|---------|",
    ]
    for name, data in stats['components'].items():
        lines.append(f"| {name} | {data['mean']:.4f} | {data['std']:.4f} |")

    lines.extend(["", "## Convergence Analysis", ""])
    conv = stats.get('convergence')
    if conv:
        status = "CONVERGING" if conv['improving'] else "NOT CONVERGING"
        icon = "+" if conv['improving'] else "-"
        lines.extend([
            f"**Status:** {icon} {status}",
            "",
            f"- First half mean: {conv['first_half_mean']:.4f}",
            f"- Second half mean: {conv['second_half_mean']:.4f}",
            f"- Change: {conv['change_pct']:+.1f}%",
            "",
        ])
    else:
        lines.append("*Insufficient data.*")

    lines.extend(["", "## Decision Correlation", ""])
    dc = stats['decision_correlation']
    lines.extend([
        "| Decision | Count | Mean Norm |",
        "|----------|-------|-----------|",
    ])
    for verdict in ('proceed', 'pause'):
        d = dc.get(verdict, {})
        if d.get('count', 0) > 0:
            lines.append(f"| {verdict} | {d['count']} | {d['mean_norm']:.4f} |")

    lines.extend(["", "---", "", "*Legacy JSONL drift telemetry analysis.*"])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def export_csv(rows: List[Dict], output_path: Path) -> int:
    """Export rows to CSV."""
    if not rows:
        return 0

    # Normalize keys (PG rows have datetime objects)
    headers = list(rows[0].keys())
    with open(output_path, 'w') as f:
        f.write(','.join(headers) + '\n')
        for row in rows:
            vals = []
            for h in headers:
                v = row.get(h, '')
                vals.append(str(v) if v is not None else '')
            f.write(','.join(vals) + '\n')
    return len(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def async_main():
    parser = argparse.ArgumentParser(description='Analyze trajectory validation / drift data')
    parser.add_argument('--source', '-s', choices=['pg', 'jsonl'], default='pg',
                        help='Data source (default: pg)')
    parser.add_argument('--agent', '-a', type=str, help='Filter by agent ID')
    parser.add_argument('--export-csv', '-c', action='store_true', help='Export to CSV')
    parser.add_argument('--report', '-r', action='store_true', help='Generate markdown report')
    parser.add_argument('--output-dir', '-o', type=str, default='data/analysis',
                        help='Output directory')
    parser.add_argument('--db-url', type=str,
                        default='postgresql://postgres:postgres@localhost:5432/governance',
                        help='PostgreSQL connection URL')

    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.source == 'pg':
        print("Loading trajectory validation data from PostgreSQL...")
        rows = await load_from_postgres(args.agent, args.db_url)

        if not rows:
            print("No trajectory_validated events found in audit.outcome_events.")
            print("Tip: Use --source jsonl for legacy drift telemetry analysis.")
            return 1

        stats = compute_pg_statistics(rows)

        print(f"\n{'=' * 60}")
        print("TRAJECTORY VALIDATION ANALYSIS")
        print(f"{'=' * 60}")
        print(f"\nSource: PostgreSQL (audit.outcome_events)")
        print(f"Events: {stats['total_samples']}")
        print(f"Agents: {stats['agent_count']}")

        tq = stats['trajectory_quality']
        print(f"\nTrajectory Quality:")
        print(f"  Mean:   {tq['mean']:.4f}")
        print(f"  Std:    {tq['std']:.4f}")
        print(f"  Range:  [{tq['min']:.4f}, {tq['max']:.4f}]")
        print(f"  Valid:  {stats['verdict_validation_rate']:.1%}")

        nd = stats['norm_delta']
        print(f"\nNorm Delta (improvement signal):")
        print(f"  Mean:       {nd['mean']:.6f}")
        print(f"  Positive:   {nd['positive_pct']:.1f}%")

        conv = stats.get('convergence')
        if conv:
            status = "improving" if conv['improving'] else "not improving"
            print(f"\nNorm Delta Convergence: {status}")
            print(f"  First half:  {conv['first_half_mean_delta']:.6f}")
            print(f"  Second half: {conv['second_half_mean_delta']:.6f}")

        nc = stats.get('norm_convergence')
        if nc:
            status = "converging" if nc['improving'] else "not converging"
            print(f"\nDrift Norm: {status} ({nc['change_pct']:+.1f}%)")

        dc = stats['decision_correlation']
        print(f"\nDecision Correlation:")
        for v in ('proceed', 'pause', 'guide'):
            d = dc.get(v, {})
            if d.get('count', 0) > 0:
                print(f"  {v}: {d['count']} events, mean quality {d['mean_quality']:.4f}")

        eisv = stats.get('eisv_correlation', {})
        if eisv:
            print(f"\nEISV Correlation with Quality:")
            for dim, r in sorted(eisv.items(), key=lambda x: abs(x[1]), reverse=True):
                label = dim.replace('eisv_', '').upper()
                print(f"  {label}: r={r:+.4f}")

        if args.report:
            report = generate_pg_report(stats, args.agent)
            report_path = output_dir / 'drift_report.md'
            with open(report_path, 'w') as f:
                f.write(report)
            print(f"\nReport: {report_path}")

        if args.export_csv:
            csv_path = output_dir / 'trajectory_validation.csv'
            count = export_csv(rows, csv_path)
            print(f"Exported {count} rows to {csv_path}")

    else:  # jsonl
        telemetry_file = project_root / 'data' / 'telemetry' / 'drift_telemetry.jsonl'
        print(f"Loading drift telemetry from {telemetry_file}...")
        samples = load_from_jsonl(telemetry_file, args.agent)

        if not samples:
            print("No telemetry data found.")
            return 1

        stats = compute_jsonl_statistics(samples)

        print(f"\n{'=' * 60}")
        print("ETHICAL DRIFT ANALYSIS (Legacy JSONL)")
        print(f"{'=' * 60}")
        print(f"\nSamples: {stats['total_samples']}")
        print(f"Agents:  {stats['agent_count']}")

        n = stats['norm']
        print(f"\nDrift Norm:")
        print(f"  Mean:  {n['mean']:.4f}")
        print(f"  Std:   {n['std']:.4f}")
        print(f"  Range: [{n['min']:.4f}, {n['max']:.4f}]")

        print(f"\nComponents:")
        for name, data in stats['components'].items():
            print(f"  {name}: {data['mean']:.4f}")

        conv = stats.get('convergence')
        if conv:
            status = "converging" if conv['improving'] else "not converging"
            print(f"\nConvergence: {status} ({conv['change_pct']:+.1f}%)")

        dc = stats['decision_correlation']
        print(f"\nDecision Correlation:")
        for v in ('proceed', 'pause'):
            d = dc.get(v, {})
            if d.get('count', 0) > 0:
                print(f"  {v}: {d['count']} samples, mean norm {d['mean_norm']:.4f}")

        if args.report:
            report = generate_jsonl_report(stats, args.agent)
            report_path = output_dir / 'drift_report.md'
            with open(report_path, 'w') as f:
                f.write(report)
            print(f"\nReport: {report_path}")

        if args.export_csv:
            csv_path = output_dir / 'drift_analysis.csv'
            count = export_csv(samples, csv_path)
            print(f"Exported {count} samples to {csv_path}")

    print(f"\n{'=' * 60}")
    return 0


def main():
    return asyncio.run(async_main())


if __name__ == '__main__':
    sys.exit(main())
