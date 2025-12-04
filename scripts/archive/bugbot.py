#!/usr/bin/env python3
"""
Bugbot - Automated Bug Status Cleanup Tool

Scans knowledge layer for bugs marked "✅ Fixed" but still "open",
suggests status updates, and optionally verifies fixes in codebase.

Usage:
    python3 scripts/bugbot.py                    # Dry run (report only)
    python3 scripts/bugbot.py --apply            # Apply fixes (requires confirmation)
    python3 scripts/bugbot.py --verify           # Also verify fixes in codebase
    python3 scripts/bugbot.py --agent-id <id>    # Check specific agent only
"""

import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import argparse

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge_layer import KnowledgeManager


# Patterns that indicate a bug is fixed (escaped for regex)
FIXED_PATTERNS = [
    r'✅\s*Fixed',
    r'✅\s*RESOLVED',
    r'✅\s*Implemented',
    r'Status.*✅.*Fixed',
    r'Status.*✅.*Resolved',
    r'\*\*Status:\*\*.*✅.*Fixed',
    r'\*\*Status:\*\*.*✅.*Resolved',
    r'\*\*Status:\*\*\s*✅\s*Fixed',
    r'\*\*Status:\*\*\s*✅\s*Resolved',
    r'\*\*Status:\*\*\s*✅\s*Implemented',
    r'\*\*Status:\*\*\s*✅\s*RESOLVED',
    r'FIXED',
    r'RESOLVED',
    r'Fixed and tested',
    r'Fixed and verified',
    r'Status.*\u2705.*Fixed',  # Unicode checkmark
    r'Status.*\u2705.*Resolved',
]


class BugBot:
    """Automated bug status cleanup tool."""
    
    def __init__(self, knowledge_dir: Optional[Path] = None):
        self.km = KnowledgeManager()
        if knowledge_dir:
            self.km.knowledge_dir = knowledge_dir
        self.mismatches: List[Dict] = []
        
    def find_mismatches(self, agent_id: Optional[str] = None) -> List[Dict]:
        """
        Find bugs marked as fixed but still open.
        
        Returns list of mismatches with:
        - agent_id
        - discovery timestamp
        - summary excerpt
        - fix evidence
        """
        mismatches = []
        
        # Query all open bugs
        discoveries = self.km.query_discoveries(
            discovery_type="bug_found",
            status="open",
            agent_id=agent_id
        )
        
        # Need to get agent_id for each discovery - load knowledge files
        knowledge_dir = self.km.data_dir
        agent_map = {}  # timestamp -> agent_id
        
        for knowledge_file in knowledge_dir.glob("*_knowledge.json"):
            agent_id_from_file = knowledge_file.stem.replace("_knowledge", "")
            knowledge = self.km.load_knowledge(agent_id_from_file)
            if knowledge:
                for disc in knowledge.discoveries:
                    agent_map[disc.timestamp] = agent_id_from_file
        
        for discovery in discoveries:
            summary = discovery.summary or ''
            details = discovery.details or ''
            combined_text = f"{summary} {details}"
            
            # Check if marked as fixed
            is_fixed = any(re.search(pattern, combined_text, re.IGNORECASE) 
                          for pattern in FIXED_PATTERNS)
            
            if is_fixed:
                disc_agent_id = agent_map.get(discovery.timestamp, 'unknown')
                mismatches.append({
                    'agent_id': disc_agent_id,
                    'timestamp': discovery.timestamp,
                    'summary': summary[:100] + '...' if len(summary) > 100 else summary,
                    'severity': discovery.severity,
                    'tags': discovery.tags or [],
                    'fix_evidence': self._extract_fix_evidence(combined_text),
                    'discovery': discovery
                })
        
        self.mismatches = mismatches
        return mismatches
    
    def _extract_fix_evidence(self, text: str) -> str:
        """Extract evidence that bug is fixed from text."""
        # Look for fix markers and surrounding context
        best_match = None
        best_start = len(text)
        
        for pattern in FIXED_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and match.start() < best_start:
                best_match = match
                best_start = match.start()
        
        if best_match:
            # Extract context around the match
            start = max(0, best_match.start() - 100)
            end = min(len(text), best_match.end() + 200)
            evidence = text[start:end].strip()
            # Clean up - remove newlines, limit length
            evidence = ' '.join(evidence.split())
            if len(evidence) > 300:
                evidence = evidence[:300] + '...'
            return evidence
        
        return ""
    
    def verify_fix_in_codebase(self, discovery_obj) -> Tuple[bool, str]:
        """
        Verify if fix is actually in codebase.
        
        Returns (is_verified, reason)
        """
        # Handle both Discovery objects and dicts
        if hasattr(discovery_obj, 'related_files'):
            related_files = discovery_obj.related_files or []
            details = discovery_obj.details or ''
        else:
            related_files = discovery_obj.get('related_files', [])
            details = discovery_obj.get('details', '')
        
        if not related_files:
            return False, "No related_files specified"
        
        # Look for file paths in details
        file_pattern = r'`([^`]+\.py)`|`([^`]+\.md)`|`([^`]+\.json)`'
        files_in_details = re.findall(file_pattern, details)
        all_files = related_files + [f for match in files_in_details for f in match if f]
        
        verified_files = []
        for file_path in all_files:
            # Try relative to project root
            full_path = Path(__file__).parent.parent / file_path
            if full_path.exists():
                verified_files.append(str(full_path))
        
        if verified_files:
            return True, f"Files exist: {', '.join(verified_files)}"
        
        return False, "Could not verify files exist"
    
    def generate_update_commands(self, verify: bool = False) -> List[str]:
        """Generate update_discovery_status commands for mismatches."""
        commands = []
        
        for mismatch in self.mismatches:
            agent_id = mismatch['agent_id']
            timestamp = mismatch['timestamp']
            summary = mismatch['summary']
            
            # Extract resolution reason from fix evidence
            fix_evidence = mismatch.get('fix_evidence', '')
            reason = f"Bug marked as fixed in summary: {fix_evidence[:100]}"
            
            if verify:
                is_verified, verify_reason = self.verify_fix_in_codebase(mismatch['discovery'])
                if is_verified:
                    reason += f" | Verified: {verify_reason}"
                else:
                    reason += f" | Not verified: {verify_reason}"
            
            # Generate MCP tool call format
            cmd = f"""mcp_governance-monitor-v1_update_discovery_status(
    agent_id="{agent_id}",
    discovery_timestamp="{timestamp}",
    new_status="resolved",
    resolved_reason="{reason}"
)"""
            commands.append(cmd)
        
        return commands
    
    def print_report(self, verify: bool = False):
        """Print a report of mismatches."""
        if not self.mismatches:
            print("✅ No mismatches found! All bug statuses are accurate.")
            return
        
        print(f"\n🔍 Found {len(self.mismatches)} bugs marked as fixed but still 'open':\n")
        print("=" * 80)
        
        for i, mismatch in enumerate(self.mismatches, 1):
            print(f"\n{i}. Agent: {mismatch['agent_id']}")
            print(f"   Timestamp: {mismatch['timestamp']}")
            print(f"   Severity: {mismatch.get('severity', 'unknown')}")
            print(f"   Tags: {', '.join(mismatch.get('tags', []))}")
            print(f"   Summary: {mismatch['summary']}")
            
            if verify:
                is_verified, reason = self.verify_fix_in_codebase(mismatch['discovery'])
                status = "✅ VERIFIED" if is_verified else "⚠️  NOT VERIFIED"
                print(f"   {status}: {reason}")
            
            print(f"   Fix Evidence: {mismatch['fix_evidence'][:150]}...")
            print()
        
        print("=" * 80)
        print(f"\nTotal: {len(self.mismatches)} bugs need status update\n")
    
    def apply_fixes(self, verify: bool = False, dry_run: bool = True):
        """Apply fixes (or show what would be applied)."""
        if not self.mismatches:
            print("✅ No fixes needed!")
            return
        
        commands = self.generate_update_commands(verify=verify)
        
        if dry_run:
            print("\n📋 Would apply these fixes:\n")
            for cmd in commands:
                print(cmd)
                print()
            print(f"\nTotal: {len(commands)} status updates")
            print("\nRun with --apply to actually update statuses")
        else:
            # Actually apply fixes
            print(f"\n⚠️  About to update {len(self.mismatches)} bug statuses...")
            response = input("Continue? (yes/no): ")
            
            if response.lower() != 'yes':
                print("Cancelled.")
                return
            
            from src.knowledge_layer import KnowledgeManager
            km = KnowledgeManager()
            
            updated = 0
            for mismatch in self.mismatches:
                try:
                    fix_evidence = mismatch.get('fix_evidence', '')
                    reason = f"Bug marked as fixed in summary: {fix_evidence[:100]}"
                    
                    if verify:
                        is_verified, verify_reason = self.verify_fix_in_codebase(mismatch['discovery'])
                        reason += f" | Verified: {verify_reason}" if is_verified else f" | Not verified: {verify_reason}"
                    
                    result = km.update_discovery_status(
                        agent_id=mismatch['agent_id'],
                        discovery_timestamp=mismatch['timestamp'],
                        new_status="resolved",
                        resolved_reason=reason
                    )
                    
                    if result:
                        updated += 1
                        print(f"✅ Updated: {mismatch['agent_id']} - {mismatch['timestamp']}")
                    else:
                        print(f"❌ Failed: {mismatch['agent_id']} - {mismatch['timestamp']}")
                except Exception as e:
                    print(f"❌ Error updating {mismatch['agent_id']}: {e}")
            
            print(f"\n✅ Updated {updated}/{len(self.mismatches)} bug statuses")


def main():
    parser = argparse.ArgumentParser(
        description="Bugbot - Automated bug status cleanup tool"
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Actually apply fixes (default: dry run)'
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify fixes exist in codebase'
    )
    parser.add_argument(
        '--agent-id',
        type=str,
        help='Check specific agent only'
    )
    parser.add_argument(
        '--knowledge-dir',
        type=str,
        help='Custom knowledge directory path'
    )
    
    args = parser.parse_args()
    
    knowledge_dir = Path(args.knowledge_dir) if args.knowledge_dir else None
    
    bot = BugBot(knowledge_dir=knowledge_dir)
    
    print("🔍 Scanning knowledge layer for bug status mismatches...")
    mismatches = bot.find_mismatches(agent_id=args.agent_id)
    
    bot.print_report(verify=args.verify)
    
    if mismatches:
        bot.apply_fixes(verify=args.verify, dry_run=not args.apply)
    
    return 0 if not mismatches else 1


if __name__ == '__main__':
    sys.exit(main())

