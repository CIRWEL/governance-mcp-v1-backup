#!/usr/bin/env python3
"""
Export agent history and mark as archived
"""

import json
import shutil
import sys
from pathlib import Path
from datetime import datetime

def export_and_archive(agent_id: str, summary: str):
    """Export governance history and update metadata to archived status"""

    print(f"\n{'='*60}")
    print(f"EXPORTING AND ARCHIVING: {agent_id}")
    print(f"{'='*60}\n")

    # 1. Export governance history
    print("1. Exporting governance history...")

    history_file = Path(f"data/governance_history_{agent_id}.csv")

    if history_file.exists():
        # Create archive directory
        archive_dir = Path("data/archive")
        archive_dir.mkdir(parents=True, exist_ok=True)

        # Copy history to archive
        archive_file = archive_dir / f"session_{agent_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        shutil.copy2(history_file, archive_file)

        print(f"   ✓ Exported to: {archive_file}")

        # Print summary stats
        with open(history_file) as f:
            lines = f.readlines()

        print(f"\n   Session Stats:")
        print(f"     Total updates: {len(lines) - 1}")  # Minus header

        # Try to parse CSV for more stats
        try:
            import csv
            with open(history_file) as f:
                reader = csv.DictReader(f)
                data = list(reader)

            if data:
                coherences = [float(row['coherence']) for row in data if 'coherence' in row]
                risks = [float(row['risk']) for row in data if 'risk' in row]
                decisions = [row['decision'] for row in data if 'decision' in row]

                if coherences:
                    print(f"     Mean coherence: {sum(coherences)/len(coherences):.3f}")
                if risks:
                    print(f"     Mean risk: {sum(risks)/len(risks):.3f}")
                if decisions:
                    from collections import Counter
                    decision_counts = Counter(decisions)
                    print(f"     Decisions: {dict(decision_counts)}")
        except Exception as e:
            print(f"     (Detailed stats unavailable: {e})")

    else:
        print(f"   ⚠ No governance history found at {history_file}")

    # 2. Save session summary
    print("\n2. Saving session summary...")

    summary_file = archive_dir / f"session_summary_{agent_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    final_state = {
        "agent_id": agent_id,
        "timestamp": datetime.now().isoformat(),
        "session_summary": summary,
        "artifacts_created": [
            "test_complexity_edge_cases.py",
            "test_rate_limiting.py",
            "COMPLEXITY_TEST_RESULTS.md",
            "scripts/record_session_discoveries.py",
            "scripts/export_and_archive_agent.py"
        ],
        "artifacts_modified": [
            "config/governance_config.py",
            "docs/reference/AI_ASSISTANT_GUIDE.md",
            "src/knowledge_graph.py",
            "FIXES_LOG.md"
        ],
        "discoveries_recorded": 5,
        "phase": "builder",
        "next_phase": "archive",
        "lifecycle_status": "session_complete_ready_for_archive"
    }

    with open(summary_file, 'w') as f:
        json.dump(final_state, f, indent=2)

    print(f"   ✓ Session summary saved: {summary_file}")

    # 3. Update agent metadata to mark as archived
    print("\n3. Updating agent metadata...")

    metadata_file = Path("data/agent_metadata.json")

    if metadata_file.exists():
        with open(metadata_file) as f:
            metadata = json.load(f)

        if agent_id in metadata:
            # Mark as non-active (archived)
            metadata[agent_id]["is_active"] = False
            metadata[agent_id]["lifecycle_state"] = "archived"
            metadata[agent_id]["archived_at"] = datetime.now().isoformat()
            metadata[agent_id]["archive_reason"] = "session_complete_builder_phase"
            metadata[agent_id]["session_summary"] = summary

            # Save updated metadata
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

            print(f"   ✓ Agent marked as archived in metadata")
            print(f"   Status: {metadata[agent_id]['lifecycle_state']}")
            print(f"   Updates: {metadata[agent_id].get('update_count', 'N/A')}")
        else:
            print(f"   ⚠ Agent not found in metadata")
    else:
        print(f"   ⚠ Metadata file not found")

    print(f"\n{'='*60}")
    print(f"EXPORT AND ARCHIVE COMPLETE")
    print(f"{'='*60}\n")

    print("✓ Governance history exported")
    print("✓ Session summary saved")
    print("✓ Agent metadata updated to archived")
    print("\nAgent lifecycle complete. Ready for handoff to archive agent.")

    return 0


if __name__ == "__main__":
    agent_id = "Ryuichi_Sakamoto_Claude_Code_20251128"

    summary = """
Multi-agent collaboration session: Reviewed Composer_Cursor's complexity derivation implementation, identified 4 issues via comprehensive edge case testing (19 tests), implemented P0-P3 fixes (documentation, weight adjustments, text normalization, verified logging). Addressed high-severity security vulnerability by implementing knowledge graph rate limiting (10 stores/hour per agent, 6/6 tests passed). Discovered validation paradox in AI governing AI (derivation moves attack surface but requires ground truth). User caught conceptual error in confidence derivation recommendation (checks and balances working). Reached natural stopping point for builder agent: diminishing returns, philosophical wall, overengineering risk. Documented agent lifecycle pattern (builder → archive phases). Created 5 files, modified 4 files, recorded 5 discoveries to knowledge graph. All tests passing, all deliverables complete. Ready for archive phase.
    """.strip()

    exit_code = export_and_archive(agent_id, summary)
    sys.exit(exit_code)
