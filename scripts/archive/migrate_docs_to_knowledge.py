#!/usr/bin/env python3
"""
⚠️ DEPRECATED - This script is obsolete.

Reason: Knowledge layer was deprecated (archived November 28, 2025).
Markdown documentation should NOT be migrated to knowledge graph (they're separate systems).

Status: Archived - kept for reference only. Use archive_old_markdowns.py instead.

Original purpose:
Migrate markdown documentation to knowledge layer.

Usage:
    python scripts/migrate_docs_to_knowledge.py --dry-run    # Preview
    python scripts/migrate_docs_to_knowledge.py              # Execute
"""

import sys
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def parse_markdown_frontmatter(content: str) -> Dict:
    """Extract YAML-style frontmatter if present."""
    frontmatter = {}
    if content.startswith('---'):
        try:
            parts = content.split('---', 2)
            if len(parts) >= 2:
                # Simple key: value parsing
                for line in parts[1].strip().split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        frontmatter[key.strip()] = value.strip()
        except:
            pass
    return frontmatter


def classify_document(filepath: Path) -> Tuple[str, str, List[str]]:
    """
    Classify document type and extract metadata.

    Returns:
        (knowledge_type, discovery_type/pattern_type, tags)
    """
    filename = filepath.stem.upper()
    parent_dir = filepath.parent.name

    tags = []

    # Extract tags from parent directory
    if parent_dir == 'analysis':
        tags.append('analysis')
    elif parent_dir == 'guides':
        tags.append('guide')
    elif parent_dir == 'proposals':
        tags.append('proposal')
    elif parent_dir == 'reference':
        tags.append('reference')

    # Classify by filename patterns
    if any(x in filename for x in ['FIX', 'BUG', 'PATCH']):
        return ('discovery', 'bug_found', tags + ['bug', 'fix'])

    if any(x in filename for x in ['INCIDENT', 'FAILURE', 'CASCADE', 'CRASH']):
        return ('discovery', 'incident', tags + ['incident'])

    if any(x in filename for x in ['ANALYSIS', 'CRITIQUE', 'REVIEW', 'ASSESSMENT']):
        return ('discovery', 'analysis', tags + ['analysis'])

    if any(x in filename for x in ['IMPROVEMENT', 'ENHANCEMENT', 'OPTIMIZATION']):
        return ('discovery', 'improvement', tags + ['improvement'])

    if any(x in filename for x in ['PATTERN', 'OBSERVATION']):
        return ('pattern', None, tags + ['pattern'])

    if 'PROPOSAL' in filename:
        return ('pattern', None, tags + ['proposal'])

    if any(x in filename for x in ['GUIDE', 'HOWTO', 'TUTORIAL']):
        return ('lesson', None, tags + ['guide'])

    # Default: treat as insight
    return ('discovery', 'insight', tags)


def extract_summary(content: str, max_length: int = 200) -> str:
    """Extract summary from markdown content."""
    # Remove frontmatter
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            content = parts[2]

    # Get first paragraph or first N characters
    lines = content.strip().split('\n')
    summary_lines = []

    for line in lines:
        line = line.strip()
        if line and not line.startswith('#'):
            summary_lines.append(line)
            if len(' '.join(summary_lines)) > max_length:
                break

    summary = ' '.join(summary_lines)
    if len(summary) > max_length:
        summary = summary[:max_length].rsplit(' ', 1)[0] + '...'

    return summary


def should_migrate(filepath: Path) -> bool:
    """Determine if file should be migrated to knowledge layer."""

    # Essential docs to keep as markdown
    essential = {
        'README.md',
        'ONBOARDING.md',
        'SYSTEM_SUMMARY.md',
        'USAGE_GUIDE.md',
        'ARCHITECTURE.md',
        'QUICK_REFERENCE.md',
        'CHANGELOG.md',
        'TROUBLESHOOTING.md',
        'AI_ASSISTANT_GUIDE.md',
        'authentication-guide.md',
        'DOCUMENTATION_GUIDELINES.md',
        'DOC_CONSOLIDATION_PLAN.md',
        'DOC_MAP.md',
        'LAYER_ARCHITECTURE.md',
    }

    # Check if essential
    if filepath.name in essential:
        return False

    # Keep guides that are comprehensive
    if filepath.parent.name == 'guides' and filepath.stat().st_size > 5000:
        return False

    # Migrate everything in archive/
    if 'archive' in filepath.parts:
        return True

    # Migrate analysis reports
    if filepath.parent.name == 'analysis':
        return True

    # Migrate most standalone docs
    if filepath.parent.name == 'docs':
        return True

    return False


def migrate_file_to_knowledge(filepath: Path, dry_run: bool = True) -> Dict:
    """
    Migrate a markdown file to knowledge layer entry.

    Returns migration record.
    """
    content = filepath.read_text()
    frontmatter = parse_markdown_frontmatter(content)

    knowledge_type, discovery_type, tags = classify_document(filepath)
    summary = extract_summary(content)

    # Create knowledge entry
    entry = {
        'agent_id': 'system_migration',
        'knowledge_type': knowledge_type,
        'title': filepath.stem.replace('_', ' ').title(),
        'summary': summary,
        'details': content,
        'tags': tags,
        'source_file': str(filepath.relative_to(project_root)),
        'migrated_at': datetime.now().isoformat(),
    }

    if discovery_type:
        entry['discovery_type'] = discovery_type

    # Extract severity from frontmatter or content
    if 'severity' in frontmatter:
        entry['severity'] = frontmatter['severity'].lower()
    elif any(x in content.upper() for x in ['CRITICAL', 'SEVERE', 'HIGH PRIORITY']):
        entry['severity'] = 'high'

    migration_record = {
        'source': str(filepath.relative_to(project_root)),
        'knowledge_entry': entry,
        'action': 'migrate' if not dry_run else 'would_migrate',
    }

    if not dry_run:
        # Actually store in knowledge layer
        from src.knowledge_layer import log_discovery, log_pattern, add_lesson

        try:
            if knowledge_type == 'discovery':
                log_discovery(
                    agent_id=entry['agent_id'],
                    discovery_type=discovery_type or 'insight',
                    summary=entry['summary'],
                    details=entry['details'],
                    tags=entry['tags'],
                    severity=entry.get('severity')
                )
            elif knowledge_type == 'pattern':
                # Generate pattern_id from title
                pattern_id = entry['title'].lower().replace(' ', '_')
                log_pattern(
                    agent_id=entry['agent_id'],
                    pattern_id=pattern_id,
                    description=entry['summary'],
                    details=entry['details'],
                    tags=entry['tags']
                )
            elif knowledge_type == 'lesson':
                # For lessons, we'll use log_discovery with type='insight'
                # since add_lesson expects just a string
                log_discovery(
                    agent_id=entry['agent_id'],
                    discovery_type='insight',
                    summary=entry['summary'],
                    details=entry['details'],
                    tags=entry['tags'] + ['lesson']
                )

            migration_record['status'] = 'success'
        except Exception as e:
            migration_record['status'] = 'failed'
            migration_record['error'] = str(e)

    return migration_record


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Migrate markdown docs to knowledge layer')
    parser.add_argument('--dry-run', action='store_true', help='Preview without executing')
    parser.add_argument('--backup', action='store_true', help='Create backup before migration')
    args = parser.parse_args()

    docs_dir = project_root / 'docs'
    markdown_files = list(docs_dir.rglob('*.md'))

    print(f"Found {len(markdown_files)} markdown files")

    # Create backup if requested
    if args.backup and not args.dry_run:
        import tarfile
        backup_path = project_root / 'data' / 'backups' / f'docs_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.tar.gz'
        backup_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"Creating backup: {backup_path}")
        with tarfile.open(backup_path, 'w:gz') as tar:
            tar.add(docs_dir, arcname='docs')
        print(f"Backup created: {backup_path}")

    # Classify files
    to_keep = []
    to_migrate = []

    for filepath in markdown_files:
        if should_migrate(filepath):
            to_migrate.append(filepath)
        else:
            to_keep.append(filepath)

    print(f"\nClassification:")
    print(f"  Keep as markdown: {len(to_keep)} files")
    print(f"  Migrate to knowledge: {len(to_migrate)} files")

    if args.dry_run:
        print("\n[DRY RUN] Would migrate these files:")
        for fp in to_migrate[:20]:  # Show first 20
            rel_path = fp.relative_to(project_root)
            k_type, d_type, tags = classify_document(fp)
            print(f"  {rel_path}")
            print(f"    → {k_type}" + (f"/{d_type}" if d_type else ""))
            print(f"    → tags: {', '.join(tags)}")

        if len(to_migrate) > 20:
            print(f"  ... and {len(to_migrate) - 20} more")
    else:
        print("\nMigrating files...")
        migration_log = []

        for i, filepath in enumerate(to_migrate, 1):
            print(f"[{i}/{len(to_migrate)}] {filepath.name}...", end=' ')
            record = migrate_file_to_knowledge(filepath, dry_run=False)
            migration_log.append(record)
            print(record['status'])

        # Save migration log
        log_path = project_root / 'data' / 'migration_log.json'
        with open(log_path, 'w') as f:
            json.dump(migration_log, f, indent=2)

        print(f"\nMigration log saved: {log_path}")

        # Print summary
        successes = sum(1 for r in migration_log if r['status'] == 'success')
        failures = sum(1 for r in migration_log if r['status'] == 'failed')

        print(f"\nMigration complete:")
        print(f"  Success: {successes}")
        print(f"  Failed: {failures}")

        if failures > 0:
            print("\nFailed migrations:")
            for r in migration_log:
                if r['status'] == 'failed':
                    print(f"  {r['source']}: {r.get('error', 'unknown error')}")


if __name__ == '__main__':
    main()
