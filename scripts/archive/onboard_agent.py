#!/usr/bin/env python3
"""
Elegant Onboarding for New Agents

Minimal interface that surfaces essential knowledge before first interaction.
Follows the principle: show what matters, hide what doesn't.

Usage:
    python3 onboard_agent.py <agent_id>
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

# Add governance MCP to path
# Auto-detect project root from script location (allows project to be anywhere)
GOVERNANCE_PATH = Path(__file__).parent.parent
# Fallback to environment variable if set
if os.getenv('GOVERNANCE_MCP_PATH'):
    GOVERNANCE_PATH = Path(os.getenv('GOVERNANCE_MCP_PATH'))
sys.path.insert(0, str(GOVERNANCE_PATH))

from src.mcp_server_std import (
    get_or_create_metadata,
    agent_metadata,
    save_metadata,
    process_update_authenticated
)


def load_knowledge_discoveries():
    """Load all discoveries from knowledge layer"""
    knowledge_dir = GOVERNANCE_PATH / "data" / "knowledge"
    if not knowledge_dir.exists():
        return []

    all_discoveries = []
    for kfile in knowledge_dir.glob("*_knowledge.json"):
        try:
            data = json.load(kfile.open())
            agent_id = data.get('agent_id', kfile.stem.replace('_knowledge', ''))
            for disc in data.get('discoveries', []):
                all_discoveries.append({
                    'agent': agent_id,
                    'timestamp': disc.get('timestamp'),
                    'type': disc.get('type'),
                    'summary': disc.get('summary'),
                    'severity': disc.get('severity'),
                    'status': disc.get('status'),
                    'resolved_at': disc.get('resolved_at')
                })
        except:
            continue

    return all_discoveries


def get_recent_discoveries(discoveries, limit=3):
    """Get most recent high-severity discoveries"""
    # Filter for resolved bugs and insights
    relevant = [d for d in discoveries
                if d['severity'] in ['high', 'critical']
                and d['status'] == 'resolved']

    # Sort by resolution date
    relevant.sort(key=lambda x: x.get('resolved_at') or x['timestamp'], reverse=True)
    return relevant[:limit]


def count_agents():
    """Count existing agents"""
    agents_dir = GOVERNANCE_PATH / "data" / "agents"
    if not agents_dir.exists():
        return 0
    return len(list(agents_dir.glob("*_state.json")))


def check_auto_logging():
    """Check if auto-logging is enabled"""
    try:
        server_file = GOVERNANCE_PATH / "src" / "mcp_server_std.py"
        content = server_file.read_text()
        if 'enabled=False' in content:
            return False
        elif 'enabled=True' in content:
            return True
    except:
        pass
    return None


def format_timestamp(ts):
    """Format timestamp elegantly"""
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d')
    except:
        return ts[:10] if ts else 'unknown'


def onboard(agent_id: str):
    """Elegant onboarding flow"""

    # Clean header
    print()
    print("═" * 60)
    print(f"  {agent_id}")
    print("═" * 60)
    print()

    # Register
    already_exists = agent_id in agent_metadata
    meta = get_or_create_metadata(agent_id)
    save_metadata()

    if already_exists:
        print(f"✓ Existing agent")
    else:
        print(f"✓ Registered")

        # Create first governance log (new agents only)
        import numpy as np
        agent_state = {
            'ethical_drift': np.array([0.0, 0.0, 0.0]),
            'response_text': "Agent registered",
            'complexity': 0.1  # Low complexity for registration
        }
        try:
            result = process_update_authenticated(
                agent_id=agent_id,
                api_key=meta.api_key,
                agent_state=agent_state,
                auto_save=True
            )
            metrics = result.get('metrics', {})
            print(f"✓ First log created (ρ={metrics.get('coherence', 0):.3f})")
        except Exception as e:
            # Don't fail onboarding if logging fails
            print(f"  (note: first log skipped - {e})", file=sys.stderr)

    print()

    # Context
    num_agents = count_agents()
    discoveries = load_knowledge_discoveries()
    recent = get_recent_discoveries(discoveries, limit=3)

    print(f"📊 {num_agents} agents tracked")
    print(f"📚 {len(discoveries)} discoveries logged")
    print()

    # Recent knowledge (minimal)
    if recent:
        print("Recent fixes:")
        for d in recent:
            date = format_timestamp(d.get('resolved_at') or d['timestamp'])
            agent = d['agent'][:20]  # Truncate long names
            summary = d['summary'][:45] + ('...' if len(d['summary']) > 45 else '')
            print(f"  • {date} | {agent}")
            print(f"    {summary}")
        print()

    # Auto-logging status
    auto_log = check_auto_logging()
    if auto_log is False:
        print("⚙️  Auto-logging: observation mode")
        print()

    # Essential reading (minimal)
    print("Before exploring:")
    print(f"  1. docs/reference/AI_ASSISTANT_GUIDE.md")
    print(f"  2. ONBOARDING.md → Day 1 (15 min)")
    print()

    # API key (only if new)
    if not already_exists:
        print("─" * 60)
        print(f"API Key: {meta.api_key}")
        print("(save this for authenticated updates)")
        print()

    print("═" * 60)
    print()


def main():
    # Handle help flags before treating as agent_id
    if len(sys.argv) < 2 or sys.argv[1] in ['--help', '-h', 'help']:
        print(__doc__)
        print("\nUsage:")
        print("  python3 onboard_agent.py <agent-id>")
        print("\nExample:")
        print("  python3 onboard_agent.py claude-sonnet-20251126")
        sys.exit(0 if len(sys.argv) > 1 else 1)

    agent_id = sys.argv[1]

    # Validate
    if not agent_id or agent_id.isspace():
        print("Error: Agent ID cannot be empty")
        sys.exit(1)

    if len(agent_id) < 2:
        print("Error: Agent ID must be at least 2 characters")
        sys.exit(1)

    try:
        onboard(agent_id)
    except Exception as e:
        print(f"✗ Onboarding failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
