#!/usr/bin/env python3
"""
Resolve the loop detection gap bug.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge_layer import KnowledgeManager

BUG_TO_RESOLVE = {
    "agent_id": "cursor_session_review_20251126",
    "timestamp": "2025-11-26T16:32:39.728974",
    "reason": "Fixed slow-stuck pattern detection gap. Added Pattern 5 (3+ updates in 60s with any reject) and Pattern 6 (5+ updates in 120s regardless of decisions). Expanded detection window from 5 to 10 updates. This catches cases like: 3 updates in 33s with 1 reject that previously slipped through Pattern 2 (which needed 2+ rejects). Updated documentation to reflect all 6 detection patterns."
}

def main():
    km = KnowledgeManager()
    
    print(f"🔄 Resolving loop detection gap bug...\n")
    
    try:
        result = km.update_discovery_status(
            agent_id=BUG_TO_RESOLVE["agent_id"],
            discovery_timestamp=BUG_TO_RESOLVE["timestamp"],
            new_status="resolved",
            resolved_reason=BUG_TO_RESOLVE["reason"]
        )
        
        if result:
            print(f"✅ Resolved: {BUG_TO_RESOLVE['agent_id']} - {BUG_TO_RESOLVE['timestamp'][:19]}")
            print(f"\nFix Summary:")
            print(f"- Added Pattern 5: Slow-stuck pattern (3+ updates in 60s with any reject)")
            print(f"- Added Pattern 6: Extended rapid pattern (5+ updates in 120s)")
            print(f"- Expanded detection window from 5 to 10 updates")
            print(f"- Updated documentation with all 6 patterns")
            print(f"\nThis fixes the gap where agents like opus_hikewa_governance_tightening_20251126")
            print(f"got stuck after rapid updates (3 updates in 33s with 1 reject) without triggering detection.")
            return 0
        else:
            print(f"❌ Bug not found")
            return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())

