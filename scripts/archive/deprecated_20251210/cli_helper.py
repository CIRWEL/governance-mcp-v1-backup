#!/usr/bin/env python3
"""
CLI Helper for Claude Code - Governance Monitor
Simple wrapper for quick governance checks from Python/CLI

Usage:
    # As a script
    python3 cli_helper.py "agent_id" "what I did" 0.5

    # As a module
    from scripts.cli_helper import quick_check
    result = quick_check("my_agent", "completed task", 0.7)
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.governance_monitor import UNITARESMonitor


def quick_check(agent_id: str, response_text: str, complexity: float = 0.5):
    """
    Quick governance check for CLI usage

    Args:
        agent_id: Your unique agent identifier
        response_text: Summary of what you did
        complexity: Complexity estimate (0.0-1.0)

    Returns:
        dict: Governance decision and metrics
    """
    monitor = UNITARESMonitor(agent_id=agent_id)
    result = monitor.process_update({
        'response_text': response_text,
        'complexity': complexity
    })
    return result


def print_result(result: dict):
    """Pretty print governance result"""
    print("\n" + "="*60)
    print("GOVERNANCE DECISION")
    print("="*60)
    print(f"Action:   {result['decision']['action'].upper()}")
    print(f"Reason:   {result['decision']['reason']}")
    if result['decision'].get('guidance'):
        print(f"Guidance: {result['decision']['guidance']}")

    print("\n" + "="*60)
    print("METRICS")
    print("="*60)
    for key, value in result['metrics'].items():
        if isinstance(value, float):
            print(f"{key:20s}: {value:.3f}")
        else:
            print(f"{key:20s}: {value}")

    if 'api_key' in result:
        print("\n" + "="*60)
        print("NEW AGENT - SAVE YOUR API KEY!")
        print("="*60)
        print(f"API Key: {result['api_key']}")

    print("\n")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 cli_helper.py <agent_id> [response_text] [complexity]")
        print("\nExample:")
        print('  python3 cli_helper.py "claude_code_cli" "Finished feature X" 0.7')
        sys.exit(1)

    agent_id = sys.argv[1]
    response_text = sys.argv[2] if len(sys.argv) > 2 else "CLI activity"
    complexity = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5

    print(f"\nChecking governance for: {agent_id}")
    print(f"Response: {response_text}")
    print(f"Complexity: {complexity}")

    result = quick_check(agent_id, response_text, complexity)
    print_result(result)
