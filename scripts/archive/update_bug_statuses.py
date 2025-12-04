#!/usr/bin/env python3
"""
Update bug statuses for bugs marked as fixed but still open.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge_layer import KnowledgeManager

# Bugs identified by bugbot.py
BUGS_TO_UPDATE = [
    {
        "agent_id": "system_migration",
        "timestamp": "2025-11-27T19:56:37.074890",
        "reason": "Bug marked as fixed in summary - Session persistence works, documentation complete"
    },
    {
        "agent_id": "system_migration",
        "timestamp": "2025-11-27T19:56:37.032478",
        "reason": "Bug marked as fixed in summary - Zombie process cleanup implemented"
    },
    {
        "agent_id": "system_migration",
        "timestamp": "2025-11-27T19:56:37.017208",
        "reason": "Bug marked as fixed in summary - λ₁ bounds enforcement and coherence calculation fixed"
    },
    {
        "agent_id": "system_migration",
        "timestamp": "2025-11-27T19:56:36.932881",
        "reason": "Bug marked as fixed in summary - Labeling fixes and completion detection implemented"
    },
    {
        "agent_id": "system_migration",
        "timestamp": "2025-11-27T19:56:36.856464",
        "reason": "Bug marked as fixed in summary - GitHub token security issue resolved"
    },
    {
        "agent_id": "system_migration",
        "timestamp": "2025-11-27T19:56:36.853889",
        "reason": "Bug marked as fixed in summary - MCP tool call timeout protection implemented"
    },
    {
        "agent_id": "composer_cursor_assistant_20251126",
        "timestamp": "2025-11-27T16:24:45.648837",
        "reason": "Bug marked as fixed in summary - Variable shadowing bug fixed in core.py"
    },
    {
        "agent_id": "composer_cursor_governance_naming_20251125",
        "timestamp": "2025-11-25T06:08:57.447666",
        "reason": "Bug marked as fixed in summary - select_reviewer TypeError fixed in dialectic.py"
    },
]

def main():
    km = KnowledgeManager()
    updated = 0
    failed = 0
    
    print(f"🔄 Updating {len(BUGS_TO_UPDATE)} bug statuses...\n")
    
    for bug in BUGS_TO_UPDATE:
        try:
            result = km.update_discovery_status(
                agent_id=bug["agent_id"],
                discovery_timestamp=bug["timestamp"],
                new_status="resolved",
                resolved_reason=bug["reason"]
            )
            
            if result:
                updated += 1
                print(f"✅ Updated: {bug['agent_id']} - {bug['timestamp'][:19]}")
            else:
                failed += 1
                print(f"❌ Not found: {bug['agent_id']} - {bug['timestamp'][:19]}")
        except Exception as e:
            failed += 1
            print(f"❌ Error updating {bug['agent_id']}: {e}")
    
    print(f"\n✅ Updated {updated}/{len(BUGS_TO_UPDATE)} bug statuses")
    if failed > 0:
        print(f"⚠️  {failed} updates failed")
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())

