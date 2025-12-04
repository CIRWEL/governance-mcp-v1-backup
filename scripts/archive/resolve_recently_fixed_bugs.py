#!/usr/bin/env python3
"""
Resolve bugs that were logged after they were already fixed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge_layer import KnowledgeManager

# Bugs that were logged AFTER they were already fixed
BUGS_TO_RESOLVE = [
    {
        "agent_id": "composer_cursor_einstein_on_the_beach_20251127",
        "timestamp": "2025-11-27T22:23:36.146432",
        "reason": "Fixed earlier today - changed check_reviewer_stuck() to use session.created_at instead of reviewer_meta.last_update"
    },
    {
        "agent_id": "composer_cursor_einstein_on_the_beach_20251127",
        "timestamp": "2025-11-27T22:23:38.128939",
        "reason": "Fixed earlier today - added Pattern 4 to detect 5+ consecutive identical decisions"
    },
    {
        "agent_id": "composer_cursor_einstein_on_the_beach_20251127",
        "timestamp": "2025-11-27T22:23:43.431386",
        "reason": "Fixed earlier today - added RISK_REJECT_THRESHOLD = 0.70 to create buffer zone between revise and reject"
    },
]

def main():
    km = KnowledgeManager()
    updated = 0
    failed = 0
    
    print(f"🔄 Resolving {len(BUGS_TO_RESOLVE)} bugs that were already fixed...\n")
    
    for bug in BUGS_TO_RESOLVE:
        try:
            result = km.update_discovery_status(
                agent_id=bug["agent_id"],
                discovery_timestamp=bug["timestamp"],
                new_status="resolved",
                resolved_reason=bug["reason"]
            )
            
            if result:
                updated += 1
                print(f"✅ Resolved: {bug['agent_id']} - {bug['timestamp'][:19]}")
            else:
                failed += 1
                print(f"❌ Not found: {bug['agent_id']} - {bug['timestamp'][:19]}")
        except Exception as e:
            failed += 1
            print(f"❌ Error updating {bug['agent_id']}: {e}")
    
    print(f"\n✅ Resolved {updated}/{len(BUGS_TO_RESOLVE)} bugs")
    if failed > 0:
        print(f"⚠️  {failed} updates failed")
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())

