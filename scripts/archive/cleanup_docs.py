#!/usr/bin/env python3
"""
Documentation cleanup script - identifies redundant, outdated, or inconsistent docs.
"""

import sys
from pathlib import Path
from collections import defaultdict
import re

def find_redundant_fix_files():
    """Find redundant fix summary files."""
    docs_dir = Path(__file__).parent.parent / "docs"
    
    fix_files = []
    for file in docs_dir.rglob("*FIX*.md"):
        if "analysis" not in str(file) and "archive" not in str(file):
            fix_files.append(file)
    
    return fix_files

def check_outdated_references():
    """Check for outdated references in docs."""
    docs_dir = Path(__file__).parent.parent / "docs"
    
    issues = []
    
    # Patterns that might indicate outdated content
    outdated_patterns = [
        (r"4.*MCP.*server", "MCP server count may be outdated"),
        (r"25.*tool", "Tool count may be outdated (should be 44+)"),
        (r"Status.*inconsistency.*bug", "Bug may be fixed"),
        (r"E.*I.*S.*history.*not.*tracked", "Feature may be implemented"),
    ]
    
    for file in docs_dir.rglob("*.md"):
        if "archive" in str(file):
            continue
            
        try:
            content = file.read_text()
            for pattern, message in outdated_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    issues.append((file, pattern, message))
        except Exception as e:
            pass
    
    return issues

def main():
    print("📚 Documentation Cleanup Analysis\n")
    print("=" * 60)
    
    # Find redundant fix files
    print("\n1. Redundant Fix Summary Files:")
    fix_files = find_redundant_fix_files()
    if fix_files:
        print(f"   Found {len(fix_files)} fix summary files:")
        for f in sorted(fix_files):
            print(f"   - {f.relative_to(Path(__file__).parent.parent)}")
        print("\n   Recommendation: Consider consolidating into FIXES_AND_INCIDENTS.md")
    else:
        print("   ✅ No redundant fix files found")
    
    # Check outdated references
    print("\n2. Potential Outdated References:")
    issues = check_outdated_references()
    if issues:
        print(f"   Found {len(issues)} potential issues:")
        for file, pattern, message in issues[:10]:  # Limit to first 10
            print(f"   - {file.name}: {message}")
        if len(issues) > 10:
            print(f"   ... and {len(issues) - 10} more")
    else:
        print("   ✅ No obvious outdated references found")
    
    print("\n" + "=" * 60)
    print("\n✅ Cleanup analysis complete")
    print("\nRecommendations:")
    print("1. Review redundant fix files - consolidate if needed")
    print("2. Update MCP_CRITIQUE.md with latest fixes")
    print("3. Archive old fix summaries that are consolidated")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())

