#!/usr/bin/env python3
"""
Resolve the health status calculation bug.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge_layer import KnowledgeManager

BUG_TO_RESOLVE = {
    "agent_id": "clair_de_lune_20251127",
    "timestamp": "2025-11-27T20:29:14.385375",
    "reason": "Fixed display mismatch - health status now clearly uses current_risk (recent trend, last 10 updates) for health calculation, not mean_risk (overall history). Updated API responses to show current_risk as primary metric (risk_score) and mean_risk as secondary (historical context). This clarifies that an agent can show 'healthy' status even if overall mean_risk is > 30%, as long as recent trend (current_risk) is < 30%."
}

def main():
    km = KnowledgeManager()
    
    print(f"🔄 Resolving health status calculation bug...\n")
    
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
            print(f"- Health status uses current_risk (recent trend, last 10) for calculation")
            print(f"- API responses now show current_risk as primary metric (risk_score)")
            print(f"- mean_risk shown as secondary metric (historical context)")
            print(f"- Updated interpretability to use current_risk for status explanations")
            return 0
        else:
            print(f"❌ Bug not found")
            return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())

