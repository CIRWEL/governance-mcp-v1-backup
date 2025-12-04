#!/usr/bin/env python3
"""
Simple Terminal Dashboard for Governance System

Real-time monitoring of fleet health, decisions, and metrics.
Uses rich library for formatted terminal output.

Usage:
    python scripts/dashboard_simple.py [--refresh SECONDS]
"""

import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from collections import Counter

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Check if rich is available
try:
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Warning: 'rich' library not found. Install with: pip install rich")
    print("Falling back to basic text output.")

def load_agent_metadata():
    """Load agent metadata from JSON file."""
    metadata_path = project_root / 'data' / 'agent_metadata.json'
    if not metadata_path.exists():
        return {}

    with open(metadata_path) as f:
        return json.load(f)

def load_agent_state(agent_id):
    """Load agent state from JSON file."""
    state_path = project_root / 'data' / 'agents' / f'{agent_id}_state.json'
    if not state_path.exists():
        return None

    try:
        with open(state_path) as f:
            return json.load(f)
    except:
        return None

def calculate_fleet_metrics(metadata):
    """Calculate aggregate fleet metrics."""
    status_counts = Counter()
    health_counts = Counter()
    decision_counts = Counter()
    coherence_scores = []
    risk_scores = []

    for agent_id, meta in metadata.items():
        # Status
        status_counts[meta.get('status', 'unknown')] += 1

        # Decisions
        decisions = meta.get('recent_decisions', [])
        for d in decisions:
            decision_counts[d] += 1

        # Load state for metrics
        state = load_agent_state(agent_id)
        if state:
            coherence_scores.append(state.get('coherence', 0))
            if 'risk_history' in state and state['risk_history']:
                risk_scores.extend(state['risk_history'][-10:])  # Last 10

    # Calculate health based on coherence
    for agent_id, meta in metadata.items():
        if meta.get('status') != 'active':
            continue

        state = load_agent_state(agent_id)
        if state:
            coherence = state.get('coherence', 0)
            if coherence >= 0.70:
                health_counts['healthy'] += 1
            elif coherence >= 0.50:
                health_counts['degraded'] += 1
            else:
                health_counts['critical'] += 1

    return {
        'total_agents': len(metadata),
        'status_counts': dict(status_counts),
        'health_counts': dict(health_counts),
        'decision_counts': dict(decision_counts),
        'mean_coherence': sum(coherence_scores) / len(coherence_scores) if coherence_scores else 0,
        'mean_risk': sum(risk_scores) / len(risk_scores) if risk_scores else 0,
        'coherence_scores': coherence_scores,
        'risk_scores': risk_scores,
    }

def create_dashboard_rich(metrics):
    """Create rich formatted dashboard."""
    console = Console()
    layout = Layout()

    # Fleet status panel
    status_table = Table(show_header=False, box=box.SIMPLE)
    status_table.add_column("Metric", style="cyan")
    status_table.add_column("Value", style="green")

    status_counts = metrics['status_counts']
    status_table.add_row("Total Agents", str(metrics['total_agents']))
    status_table.add_row("Active", str(status_counts.get('active', 0)))
    status_table.add_row("Paused", str(status_counts.get('paused', 0)))
    status_table.add_row("Archived", str(status_counts.get('archived', 0)))
    status_table.add_row("Waiting Input", str(status_counts.get('waiting_input', 0)))

    # Health panel
    health_table = Table(show_header=False, box=box.SIMPLE)
    health_table.add_column("Health", style="cyan")
    health_table.add_column("Count", style="green")

    health_counts = metrics['health_counts']
    health_table.add_row("Healthy", str(health_counts.get('healthy', 0)))
    health_table.add_row("Degraded", str(health_counts.get('degraded', 0)))
    health_table.add_row("Critical", str(health_counts.get('critical', 0)))

    # Decisions panel with bar chart
    decision_counts = metrics['decision_counts']
    total_decisions = sum(decision_counts.values())

    decision_text = []
    if total_decisions > 0:
        approve_pct = (decision_counts.get('approve', 0) / total_decisions) * 100
        revise_pct = (decision_counts.get('revise', 0) / total_decisions) * 100
        reject_pct = (decision_counts.get('reject', 0) / total_decisions) * 100

        decision_text.append(f"Approve: {approve_pct:5.1f}% {'█' * int(approve_pct / 2)}")
        decision_text.append(f"Revise:  {revise_pct:5.1f}% {'█' * int(revise_pct / 2)}")
        decision_text.append(f"Reject:  {reject_pct:5.1f}% {'█' * int(reject_pct / 2)}")
    else:
        decision_text.append("No recent decisions")

    # Metrics panel
    coherence = metrics['mean_coherence']
    risk = metrics['mean_risk']

    coherence_status = "✓" if coherence >= 0.70 else "⚠️" if coherence >= 0.50 else "❌"
    risk_status = "✓" if risk < 0.30 else "⚠️" if risk < 0.50 else "❌"

    metrics_text = [
        f"Mean Coherence: {coherence:.3f} (Target: 0.85) {coherence_status}",
        f"Mean Risk:      {risk:.3f} (Revise: <0.50) {risk_status}",
    ]

    # Build panels
    panels = [
        Panel(status_table, title="Fleet Status", border_style="blue"),
        Panel(health_table, title="Fleet Health", border_style="green"),
        Panel("\n".join(decision_text), title="Recent Decisions", border_style="yellow"),
        Panel("\n".join(metrics_text), title="System Metrics", border_style="magenta"),
    ]

    # Top active agents
    metadata = load_agent_metadata()
    active_agents = [(aid, meta) for aid, meta in metadata.items()
                     if meta.get('status') == 'active']
    active_agents.sort(key=lambda x: x[1].get('last_update', ''), reverse=True)

    agents_table = Table(show_header=True, box=box.SIMPLE)
    agents_table.add_column("Agent ID", style="cyan")
    agents_table.add_column("Status", style="green")
    agents_table.add_column("Updates", style="yellow")

    for agent_id, meta in active_agents[:5]:
        status_icon = "🟢" if meta.get('status') == 'active' else "🟡"
        agents_table.add_row(
            agent_id[:40],
            status_icon,
            str(meta.get('total_updates', 0))
        )

    panels.append(Panel(agents_table, title="Top 5 Active Agents", border_style="cyan"))

    # Clear screen and render
    console.clear()
    console.print("\n[bold cyan]UNITARES Governance Dashboard[/bold cyan]")
    console.print(f"[dim]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]\n")

    for panel in panels:
        console.print(panel)

    console.print("\n[dim]Press Ctrl+C to quit[/dim]")

def create_dashboard_basic(metrics):
    """Create basic text dashboard (no rich library)."""
    print("\n" * 50)  # Clear screen
    print("=" * 60)
    print("UNITARES Governance Dashboard")
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    # Fleet status
    print("Fleet Status:")
    print(f"  Total Agents: {metrics['total_agents']}")
    for status, count in metrics['status_counts'].items():
        print(f"  {status.title()}: {count}")
    print()

    # Health
    print("Fleet Health:")
    for health, count in metrics['health_counts'].items():
        print(f"  {health.title()}: {count}")
    print()

    # Decisions
    decision_counts = metrics['decision_counts']
    total_decisions = sum(decision_counts.values())
    print("Recent Decisions:")
    if total_decisions > 0:
        for decision in ['approve', 'revise', 'reject']:
            count = decision_counts.get(decision, 0)
            pct = (count / total_decisions) * 100
            bar = '#' * int(pct / 2)
            print(f"  {decision.title():8} {pct:5.1f}% {bar}")
    else:
        print("  No recent decisions")
    print()

    # Metrics
    coherence = metrics['mean_coherence']
    risk = metrics['mean_risk']
    print("System Metrics:")
    print(f"  Mean Coherence: {coherence:.3f} (Target: 0.85)")
    print(f"  Mean Risk:      {risk:.3f} (Revise threshold: 0.50)")
    print()

    print("-" * 60)
    print("Press Ctrl+C to quit")

def main():
    parser = argparse.ArgumentParser(description='Governance system dashboard')
    parser.add_argument('--refresh', type=int, default=5, help='Refresh interval in seconds')
    parser.add_argument('--basic', action='store_true', help='Use basic text output')
    args = parser.parse_args()

    use_rich = RICH_AVAILABLE and not args.basic

    try:
        while True:
            # Load data
            metadata = load_agent_metadata()
            metrics = calculate_fleet_metrics(metadata)

            # Display
            if use_rich:
                create_dashboard_rich(metrics)
            else:
                create_dashboard_basic(metrics)

            # Wait for next refresh
            time.sleep(args.refresh)

    except KeyboardInterrupt:
        print("\nDashboard stopped.")
        sys.exit(0)

if __name__ == '__main__':
    main()
