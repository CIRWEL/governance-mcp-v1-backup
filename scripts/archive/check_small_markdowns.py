#!/usr/bin/env python3
"""
Check for small markdown files that should use knowledge layer instead.

Usage:
    python3 scripts/check_small_markdowns.py                    # List small files
    python3 scripts/check_small_markdowns.py --suggest-migration # Show migration suggestions
    python3 scripts/check_small_markdowns.py --migrate          # Auto-migrate (dry-run by default)
"""

import sys
from pathlib import Path
from typing import List, Tuple
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Essential docs that should stay as markdown regardless of size
ESSENTIAL_DOCS = {
    'README.md', 'CHANGELOG.md',  # Root files only
    # Moved to docs/: ONBOARDING.md, SYSTEM_SUMMARY.md, USAGE_GUIDE.md, ARCHITECTURE.md
    'DOCUMENTATION_GUIDELINES.md', 'DOC_MAP.md', 'ORGANIZATION_GUIDE.md',
    'SECURITY_AUDIT.md', 'RELEASE_NOTES_v2.0.md', 'ROADMAP_TO_10_10.md',
    'HANDOFF.md', 'END_TO_END_FLOW.md', 'AUTOMATIC_RECOVERY.md',
    'CIRCUIT_BREAKER_DIALECTIC.md', 'DIALECTIC_COORDINATION.md',
    'DIALECTIC_IMPROVEMENTS.md', 'CONFIDENCE_GATING_AND_CALIBRATION.md',
    'BACKUP_STRATEGY.md', 'DOCUMENTATION_COHERENCE.md', 'META_PATTERNS.md',
    'AGI_FRIENDLINESS_ASSESSMENT.md', 'AGI_FRIENDLINESS_IMPROVEMENTS.md',
    'authentication-guide.md', 'knowledge-layer.md'
}

# Threshold: 1000 words ≈ 5000 characters
WORD_THRESHOLD = 1000
CHAR_THRESHOLD = 5000

# Directories to skip (comprehensive reference docs)
SKIP_DIRS = {'guides', 'architecture', 'reference', 'archive'}


def count_words(content: str) -> int:
    """Count words in content."""
    return len(content.split())


def find_small_markdowns(docs_dir: Path) -> List[Tuple[Path, int, int]]:
    """Find markdown files that are too small."""
    small_files = []
    
    for md_file in docs_dir.rglob('*.md'):
        # Skip essential docs
        if md_file.name in ESSENTIAL_DOCS:
            continue
        
        # Skip archive
        if 'archive' in md_file.parts:
            continue
        
        # Skip comprehensive reference directories
        if any(skip_dir in md_file.parts for skip_dir in SKIP_DIRS):
            continue
        
        # Count words
        try:
            content = md_file.read_text(encoding='utf-8', errors='ignore')
            word_count = count_words(content)
            char_count = len(content)
            
            # If under threshold, flag it
            if word_count < WORD_THRESHOLD and char_count < CHAR_THRESHOLD:
                small_files.append((md_file, word_count, char_count))
        except Exception as e:
            print(f"⚠️  Error reading {md_file}: {e}", file=sys.stderr)
    
    return sorted(small_files, key=lambda x: x[1])  # Sort by word count


def classify_content(content: str) -> Tuple[str, str, List[str]]:
    """Classify content to determine knowledge type and discovery type."""
    content_lower = content.lower()
    
    # Determine discovery type
    if 'bug' in content_lower or 'error' in content_lower or 'fix' in content_lower:
        discovery_type = 'bug_found'
    elif 'insight' in content_lower or 'observation' in content_lower or 'finding' in content_lower:
        discovery_type = 'insight'
    elif 'pattern' in content_lower or 'recurring' in content_lower:
        discovery_type = 'pattern'
    elif 'improvement' in content_lower or 'enhancement' in content_lower or 'optimization' in content_lower:
        discovery_type = 'improvement'
    elif 'question' in content_lower or '?' in content:
        discovery_type = 'question'
    else:
        discovery_type = 'insight'  # Default
    
    # Extract tags
    tags = []
    if 'security' in content_lower:
        tags.append('security')
    if 'performance' in content_lower:
        tags.append('performance')
    if 'governance' in content_lower:
        tags.append('governance')
    if 'architecture' in content_lower:
        tags.append('architecture')
    if 'bug' in content_lower:
        tags.append('bug')
    
    # Determine severity
    severity = 'low'
    if 'critical' in content_lower or 'severe' in content_lower:
        severity = 'critical'
    elif 'high' in content_lower or 'important' in content_lower:
        severity = 'high'
    elif 'medium' in content_lower:
        severity = 'medium'
    
    return discovery_type, severity, tags


def suggest_migration(filepath: Path, word_count: int, char_count: int):
    """Suggest how to migrate a small markdown file to knowledge layer."""
    rel_path = filepath.relative_to(project_root)
    content = filepath.read_text(encoding='utf-8', errors='ignore')
    
    # Extract summary (first line or first sentence)
    lines = content.split('\n')
    summary = lines[0].strip('#').strip() if lines else filepath.stem.replace('_', ' ').title()
    if len(summary) > 200:
        summary = summary[:200].rsplit(' ', 1)[0] + '...'
    
    discovery_type, severity, tags = classify_content(content)
    
    print(f"\n📄 {rel_path}")
    print(f"   Size: {word_count} words, {char_count} chars")
    print(f"\n   Suggested migration:")
    print(f"   ```python")
    print(f"   store_knowledge(")
    print(f"       agent_id='your_agent_id',")
    print(f"       knowledge_type='discovery',")
    print(f"       discovery_type='{discovery_type}',")
    print(f"       summary='{summary}',")
    print(f"       details='''{content[:500]}...''',")
    print(f"       severity='{severity}',")
    print(f"       tags={tags}")
    print(f"   )")
    print(f"   ```")
    print(f"\n   Then delete: {rel_path}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Check for small markdown files that should use knowledge layer'
    )
    parser.add_argument('--suggest-migration', action='store_true',
                       help='Show migration suggestions for each file')
    parser.add_argument('--migrate', action='store_true',
                       help='Auto-migrate files (dry-run by default)')
    parser.add_argument('--execute', action='store_true',
                       help='Actually execute migration (requires --migrate)')
    args = parser.parse_args()
    
    docs_dir = project_root / 'docs'
    if not docs_dir.exists():
        print(f"❌ Docs directory not found: {docs_dir}")
        sys.exit(1)
    
    small_files = find_small_markdowns(docs_dir)
    
    if not small_files:
        print("✅ No small markdown files found!")
        return 0
    
    print(f"📊 Found {len(small_files)} small markdown files (< {WORD_THRESHOLD} words):\n")
    
    if args.suggest_migration:
        for filepath, word_count, char_count in small_files:
            suggest_migration(filepath, word_count, char_count)
    elif args.migrate:
        print("⚠️  Migration not yet implemented.")
        print("   Use --suggest-migration to see how to migrate manually.")
        print("   Or use scripts/migrate_docs_to_knowledge.py for bulk migration.")
    else:
        # Just list them
        for filepath, word_count, char_count in small_files:
            rel_path = filepath.relative_to(project_root)
            print(f"  • {rel_path} ({word_count} words, {char_count} chars)")
        
        print(f"\n💡 Tip: Run with --suggest-migration to see migration suggestions")
        print(f"   Or see docs/DOCUMENTATION_GUIDELINES.md for when to use knowledge layer")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

