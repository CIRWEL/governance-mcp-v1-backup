#!/usr/bin/env python3
"""
Validate consistency between metadata, state files, and knowledge layers.

Checks:
- Agents with updates have corresponding state files
- State file data matches metadata claims
- No orphaned files
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class ValidationResult:
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

    def add_error(self, msg: str):
        self.errors.append(f"❌ ERROR: {msg}")

    def add_warning(self, msg: str):
        self.warnings.append(f"⚠️  WARNING: {msg}")

    def add_info(self, msg: str):
        self.info.append(f"ℹ️  INFO: {msg}")

    def print_report(self):
        print("="*70)
        print("LAYER CONSISTENCY VALIDATION")
        print("="*70)

        if self.errors:
            print("\n🔴 ERRORS:")
            for err in self.errors:
                print(f"  {err}")

        if self.warnings:
            print("\n🟡 WARNINGS:")
            for warn in self.warnings:
                print(f"  {warn}")

        if self.info:
            print("\n🔵 INFO:")
            for info in self.info:
                print(f"  {info}")

        print("\n" + "="*70)
        print(f"Summary: {len(self.errors)} errors, {len(self.warnings)} warnings")
        print("="*70)

        return len(self.errors) == 0


def validate_metadata_state_consistency(result: ValidationResult) -> None:
    """Validate metadata ↔ state file consistency"""

    # Load metadata
    meta_file = project_root / "data" / "agent_metadata.json"
    if not meta_file.exists():
        result.add_error("agent_metadata.json not found")
        return

    try:
        metadata = json.load(open(meta_file))
    except json.JSONDecodeError as e:
        result.add_error(f"agent_metadata.json is invalid JSON: {e}")
        return

    result.add_info(f"Found {len(metadata)} agents in metadata")

    # Check each agent
    agents_with_updates = 0
    valid_state_files = 0
    missing_state_files = []

    for agent_id, meta in metadata.items():
        total_updates = meta.get('total_updates', 0)

        if total_updates > 0:
            agents_with_updates += 1

            # CORRECTED: Check state files in data/agents/
            state_file = project_root / "data" / "agents" / f"{agent_id}_state.json"

            if state_file.exists():
                valid_state_files += 1

                # Validate state file content
                try:
                    state_data = json.load(open(state_file))
                    state_update_count = state_data.get('update_count', 0)

                    # Check update count matches
                    if state_update_count != total_updates:
                        result.add_warning(
                            f"Agent '{agent_id}': metadata claims {total_updates} updates "
                            f"but state file has {state_update_count}"
                        )

                    # Check history arrays are consistent
                    history_lengths = {
                        'E': len(state_data.get('E_history', [])),
                        'I': len(state_data.get('I_history', [])),
                        'S': len(state_data.get('S_history', [])),
                        'V': len(state_data.get('V_history', [])),
                        'coherence': len(state_data.get('coherence_history', []))
                    }

                    if len(set(history_lengths.values())) > 1:
                        result.add_warning(
                            f"Agent '{agent_id}': history arrays have inconsistent lengths: {history_lengths}"
                        )

                except json.JSONDecodeError:
                    result.add_error(f"Agent '{agent_id}': state file is corrupted")
                except Exception as e:
                    result.add_warning(f"Agent '{agent_id}': error reading state file: {e}")

            else:
                missing_state_files.append((agent_id, total_updates))

    # Report summary
    result.add_info(f"Agents with updates: {agents_with_updates}")
    result.add_info(f"Valid state files: {valid_state_files}")

    if missing_state_files:
        result.add_warning(f"{len(missing_state_files)} agents missing state files:")
        for agent_id, updates in missing_state_files[:10]:
            result.add_warning(f"  • {agent_id} (expected {updates} data points)")


def validate_orphaned_files(result: ValidationResult) -> None:
    """Find state files without corresponding metadata entries"""

    meta_file = project_root / "data" / "agent_metadata.json"
    if not meta_file.exists():
        return

    metadata = json.load(open(meta_file))
    agent_ids = set(metadata.keys())

    # Check for orphaned state files
    agents_dir = project_root / "data" / "agents"
    if agents_dir.exists():
        orphaned = []
        for state_file in agents_dir.glob("*_state.json"):
            agent_id = state_file.stem.replace('_state', '')
            if agent_id not in agent_ids:
                orphaned.append(agent_id)

        if orphaned:
            result.add_warning(f"{len(orphaned)} orphaned state files (no metadata):")
            for agent_id in orphaned[:5]:
                result.add_warning(f"  • {agent_id}")


def validate_governance_update_patterns(result: ValidationResult) -> None:
    """Analyze which agents are avoiding governance updates"""

    meta_file = project_root / "data" / "agent_metadata.json"
    if not meta_file.exists():
        return

    metadata = json.load(open(meta_file))

    # Find active agents with zero updates
    zero_update_active = []
    for agent_id, meta in metadata.items():
        if meta.get('status') == 'active' and meta.get('total_updates', 0) == 0:
            zero_update_active.append(agent_id)

    if zero_update_active:
        result.add_warning(
            f"{len(zero_update_active)} ACTIVE agents with ZERO governance updates:"
        )
        result.add_warning(
            "  These agents may be working 'under the radar' without oversight"
        )
        for agent_id in zero_update_active[:5]:
            result.add_warning(f"  • {agent_id}")


def main():
    result = ValidationResult()

    # Run validations
    validate_metadata_state_consistency(result)
    validate_orphaned_files(result)
    validate_governance_update_patterns(result)

    # Print report
    success = result.print_report()

    # Exit code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
