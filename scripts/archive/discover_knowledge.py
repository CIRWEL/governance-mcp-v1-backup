#!/usr/bin/env python3
"""
Knowledge Discovery - Minimal Interface

Surface relevant discoveries from the knowledge layer.
Shows what others learned so you don't repeat mistakes.

Usage:
    python3 discover_knowledge.py [--topic coherence|threshold|bug]
    python3 discover_knowledge.py --recent
    python3 discover_knowledge.py --critical
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Auto-detect project root from script location (allows project to be anywhere)
GOVERNANCE_PATH = Path(__file__).parent.parent
# Fallback to environment variable if set
import os
if os.getenv('GOVERNANCE_MCP_PATH'):
    GOVERNANCE_PATH = Path(os.getenv('GOVERNANCE_MCP_PATH'))


def load_all_knowledge():
    """Load knowledge from all agents"""
    knowledge_dir = GOVERNANCE_PATH / "data" / "knowledge"
    if not knowledge_dir.exists():
        return []

    all_items = []
    for kfile in knowledge_dir.glob("*_knowledge.json"):
        try:
            data = json.load(kfile.open())
            agent_id = data.get('agent_id', kfile.stem.replace('_knowledge', ''))

            # Discoveries
            for disc in data.get('discoveries', []):
                all_items.append({
                    'type': 'discovery',
                    'agent': agent_id,
                    'subtype': disc.get('type'),
                    'summary': disc.get('summary'),
                    'details': disc.get('details'),
                    'severity': disc.get('severity'),
                    'status': disc.get('status'),
                    'tags': disc.get('tags', []),
                    'timestamp': disc.get('timestamp'),
                    'resolved_at': disc.get('resolved_at')
                })

            # Patterns
            for pattern in data.get('patterns', []):
                all_items.append({
                    'type': 'pattern',
                    'agent': agent_id,
                    'summary': pattern.get('description'),
                    'severity': pattern.get('severity'),
                    'tags': pattern.get('tags', []),
                    'timestamp': pattern.get('first_observed'),
                    'occurrences': pattern.get('occurrences')
                })

            # Lessons
            for lesson in data.get('lessons_learned', []):
                all_items.append({
                    'type': 'lesson',
                    'agent': agent_id,
                    'summary': lesson,
                    'timestamp': data.get('last_updated')
                })

        except Exception as e:
            continue

    return all_items


def format_date(ts):
    """Minimal date format"""
    if not ts:
        return ''
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d')
    except:
        return ts[:10] if len(ts) >= 10 else ts


def filter_by_topic(items, topic):
    """Filter by topic/tag"""
    topic_lower = topic.lower()
    return [item for item in items
            if topic_lower in str(item.get('summary', '')).lower()
            or topic_lower in [t.lower() for t in item.get('tags', [])]]


def filter_recent(items, days=7):
    """Get recent items"""
    now = datetime.now()
    recent = []
    for item in items:
        ts = item.get('resolved_at') or item.get('timestamp')
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            if (now - dt).days <= days:
                recent.append(item)
        except:
            continue
    return recent


def filter_critical(items):
    """Get critical/high severity items"""
    return [item for item in items
            if item.get('severity') in ['critical', 'high']]


def print_item(item, show_details=False):
    """Print single item elegantly"""
    # Icon by type
    icons = {
        'discovery': '•',
        'pattern': '~',
        'lesson': '→'
    }
    icon = icons.get(item['type'], '·')

    # Status indicator
    status = ''
    if item.get('status') == 'resolved':
        status = '✓ '
    elif item.get('status') == 'open':
        status = '○ '

    # Date
    date = format_date(item.get('resolved_at') or item.get('timestamp'))

    # Agent (truncated)
    agent = item['agent'][:18]

    # Summary (truncated)
    summary = item['summary']
    if len(summary) > 50 and not show_details:
        summary = summary[:47] + '...'

    print(f"  {icon} {status}{date} | {agent}")
    print(f"    {summary}")

    if show_details and item.get('details'):
        # Show first 2 lines of details
        details_lines = item['details'].split('\n')[:2]
        for line in details_lines:
            if line.strip():
                print(f"    {line.strip()[:70]}")

    print()


def show_recent(items):
    """Show recent discoveries"""
    print()
    print("Recent (last 7 days)")
    print("─" * 60)
    recent = filter_recent(items)
    recent.sort(key=lambda x: x.get('resolved_at') or x.get('timestamp', ''), reverse=True)

    if not recent:
        print("  (none)")
    else:
        for item in recent[:10]:
            print_item(item)


def show_critical(items):
    """Show critical issues"""
    print()
    print("Critical & High Severity")
    print("─" * 60)
    critical = filter_critical(items)
    critical.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

    if not critical:
        print("  (none)")
    else:
        for item in critical[:10]:
            print_item(item, show_details=True)


def show_by_topic(items, topic):
    """Show items by topic"""
    print()
    print(f"Topic: {topic}")
    print("─" * 60)
    filtered = filter_by_topic(items, topic)
    filtered.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

    if not filtered:
        print(f"  (no discoveries about '{topic}')")
    else:
        for item in filtered[:10]:
            print_item(item, show_details=True)


def show_summary(items):
    """Show summary stats"""
    print()
    print("Knowledge Layer Summary")
    print("═" * 60)

    # Count by type
    by_type = defaultdict(int)
    for item in items:
        by_type[item['type']] += 1

    # Count by severity
    by_severity = defaultdict(int)
    for item in items:
        sev = item.get('severity')
        if sev:
            by_severity[sev] += 1

    # Count resolved vs open
    resolved = len([i for i in items if i.get('status') == 'resolved'])
    open_items = len([i for i in items if i.get('status') == 'open'])

    print(f"  Total: {len(items)} items")
    print()
    print(f"  Discoveries: {by_type['discovery']}")
    print(f"  Patterns: {by_type['pattern']}")
    print(f"  Lessons: {by_type['lesson']}")
    print()
    print(f"  Critical: {by_severity['critical']}")
    print(f"  High: {by_severity['high']}")
    print(f"  Medium: {by_severity['medium']}")
    print()
    print(f"  Resolved: {resolved}")
    print(f"  Open: {open_items}")
    print()
    print("═" * 60)
    print()


def main():
    items = load_all_knowledge()

    if not items:
        print("No knowledge discovered yet.")
        sys.exit(0)

    # Parse args
    if len(sys.argv) == 1:
        show_summary(items)
        return

    arg = sys.argv[1]

    if arg == '--recent':
        show_recent(items)
    elif arg == '--critical':
        show_critical(items)
    elif arg.startswith('--topic='):
        topic = arg.split('=', 1)[1]
        show_by_topic(items, topic)
    elif arg == '--help' or arg == '-h':
        print(__doc__)
    else:
        # Treat as topic
        show_by_topic(items, arg)


if __name__ == "__main__":
    main()
