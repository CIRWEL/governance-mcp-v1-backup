#!/usr/bin/env python3
"""
Generate ORGANIZATION_GUIDE.md with proper dynamic dates.
This ensures dates are never hardcoded.
"""

from datetime import datetime
from pathlib import Path


def generate_organization_guide():
    """Generate the organization guide with current date."""

    # Get current date dynamically
    current_date = datetime.now().strftime("%B %d, %Y")

    content = f"""# Organization Guide

**Created:** {current_date}
**Last Updated:** {current_date}
**Purpose:** Single source of truth for data and docs organization
**Status:** Active

---

## Overview

This guide documents the current organization of the governance-mcp-v1 project. It follows the principle: **ONE file, not many**. This replaces separate data/docs organization protocols to reduce maintenance burden.

---

## Data Directory (`data/`)

### Current Structure (Organized)

The `data/` directory uses an **organized structure** with subdirectories:

```
data/
├── agent_metadata.json           # ⚠️  NOT in git (contains API keys)
├── audit_log.jsonl               # ⚠️  NOT in git (sensitive)
│
├── agents/                        # Agent state files
│   └── {{agent_id}}_state.json
│
├── history/                       # Historical exports
│   └── {{agent_id}}_history_{{timestamp}}.{{ext}}
│
├── knowledge/                     # Knowledge layer (⚠️ NOT in git)
├── dialectic_sessions/            # Dialectic recovery sessions
├── archive/                       # Archived data (⚠️ NOT in git)
│   ├── agents/                    # Archived agent states
│   ├── history/                   # Archived history files
│   └── exports/                   # Archived exports
├── processes/                     # Process tracking (⚠️ NOT in git)
├── locks/                         # Runtime locks (⚠️ NOT in git)
└── test_files/                    # Test data (✅ safe for git)
```

### File Naming Patterns

**Agent States:** `agents/{{agent_id}}_state.json`
- Examples: `agents/scout_state.json`, `agents/glass_state.json`
- Location: `data/agents/` subdirectory

**History Exports:** `history/{{agent_id}}_history_{{timestamp}}.{{ext}}`
- Examples: `history/scout_history_20251125_120000.json`
- Location: `data/history/` subdirectory

**Knowledge:** Stored in `knowledge/` subdirectory

**Test Files:** Prefix with `test_` and store in `test_files/` subdirectory

### Automatic Migration

The system includes **automatic migration** from old flat structure to new organized structure:

- When a state file is accessed, if it exists in the old location (`data/{{agent_id}}_state.json`), it will be automatically moved to the new location (`data/agents/{{agent_id}}_state.json`)
- This happens transparently on first access
- No manual migration needed for active agents

### Git Safety

**⚠️  NOT in git:**
- `agent_metadata.json` (contains API keys)
- `audit_log.jsonl` (may contain sensitive data)
- `knowledge/` (may contain sensitive discoveries)
- `processes/`, `locks/` (runtime state)

**✅ Safe for git:**
- `test_files/` (test data only, no real keys)
- `agent_metadata.example.json` (template)
- Documentation files

### Cleanup Guidelines

**When to archive:**
- Agent inactive >30 days: Consider archiving state
- History exports >90 days: Consider moving to `archive/` or external backup
- Test files: Keep last 10, delete older

**How to archive:**
1. Create `data/archive/` if needed: `mkdir -p data/archive/{{agents,exports}}`
2. Move old files: `mv {{agent_id}}_state.json archive/agents/`
3. Update `agent_metadata.json` to reflect archived status

---

## Docs Directory (`docs/`)

### Current Structure (Organized)

The `docs/` directory already has subdirectories:

```
docs/
├── guides/              # How-to guides for users
├── reference/           # Technical reference docs
├── analysis/            # Analysis and research reports
├── archive/             # Historical/superseded docs
└── [root files]         # Active protocols and status docs
```

### Document Categories

**`guides/`** - Step-by-step instructions
- MCP setup, authentication, troubleshooting
- User-facing documentation

**`reference/`** - Technical reference
- Architecture docs, API reference
- README_FOR_FUTURE_CLAUDES.md

**`analysis/`** - Research and findings
- Coherence analysis, test results
- Investigation reports

**`archive/`** - Historical documentation
- Old status reports, superseded docs
- Session summaries

**Root-level** - Current status and protocols
- This file (ORGANIZATION_GUIDE.md)
- RELEASE_NOTES, SECURITY_AUDIT, etc.

### Documentation Guidelines

**Use markdown files for:**
- Comprehensive reports (1000+ words)
- User guides and reference documentation
- Protocols and standards

**Use knowledge layer (`store_knowledge`) for:**
- Bugs, insights, patterns
- Discrete discoveries
- Questions and lessons learned

See [DOCUMENTATION_GUIDELINES.md](DOCUMENTATION_GUIDELINES.md) for details.

### Cleanup Guidelines

**When to archive:**
- Document >90 days old AND superseded by newer version
- Document is historical reference only
- No longer relevant to current version

**Where to archive:**
- General docs → `docs/archive/`
- Session summaries → `docs/archive/sessions/`
- Consolidated historical docs → `docs/archive/consolidated/`

---

## Key Principles

### 1. ONE File Principle
**Don't create multiple organization files.** This guide is the single source of truth. Update it in place.

### 2. Dynamic Dates
**Never hardcode dates in documentation.** Use generation scripts or date utilities.

**For this project:** Use `datetime.now().strftime("%B %d, %Y")` in Python scripts.

**For workspace-level docs:** Use `/Users/cirwel/scripts/utils/date_utils.py`

### 3. Document Reality, Not Aspirations
**Document what IS, not what should be.** If proposing changes, implement them before documenting.

### 4. Flat Is Better Than Nested (For Data)
The current flat structure in `data/` works well. File naming conventions provide organization without code changes.

**Don't create subdirectories unless there's a compelling reason AND you've verified all code paths.**

### 5. Knowledge Layer vs Markdown
- **Knowledge layer:** Quick discoveries, bugs, insights (use MCP `store_knowledge` tool)
- **Markdown:** Comprehensive guides, reports, reference docs

---

## Migration Status

**✅ Migration completed!** The data directory has been organized.

**What changed:**
- State files moved from `data/` to `data/agents/`
- History files moved from `data/` to `data/history/`
- Created `data/archive/` structure for old files
- Updated code to use new paths with backward compatibility

**Automatic migration:**
- Code automatically migrates files on first access
- No manual intervention needed for remaining files
- Falls back gracefully if migration fails

---

## Quick Reference

**Where do I put...?**

**Data files:**
- Agent state → `data/agents/{{agent_id}}_state.json`
- History export → `data/history/{{agent_id}}_history_{{timestamp}}.json`
- Knowledge → `data/knowledge/{{agent_id}}_knowledge.json`
- Test data → `data/test_files/test_*.json`
- Archived agent → `data/archive/agents/{{agent_id}}_state.json`
- Archived history → `data/archive/history/{{agent_id}}_history_{{timestamp}}.json`

**Documentation:**
- User guide → `docs/guides/TITLE.md`
- Technical reference → `docs/reference/TITLE.md`
- Analysis report → `docs/analysis/TITLE.md`
- Current protocol → `docs/TITLE.md` (root level)
- Bug/insight → Use `store_knowledge` MCP tool

**When do I archive?**
- Data: Agent inactive >30 days, exports >90 days
- Docs: >90 days old AND superseded

---

## Maintenance

**Regenerate this file:**
```bash
python3 scripts/generate_org_guide.py
```

This ensures dates stay current without manual updates.

**Last generated:** {current_date}

---

## See Also

- [DOCUMENTATION_GUIDELINES.md](docs/DOCUMENTATION_GUIDELINES.md) - Knowledge layer vs markdown
- [README.md](README.md) - Project overview
- [data/README.md](data/README.md) - Data directory quick reference
"""

    return content


def main():
    """Generate and write the organization guide."""
    # Get project root (parent of scripts/)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    output_path = project_root / "docs" / "ORGANIZATION_GUIDE.md"

    # Generate content
    content = generate_organization_guide()

    # Write to file
    output_path.write_text(content)

    print(f"✅ Generated: {output_path}")
    print(f"📅 Date: {datetime.now().strftime('%B %d, %Y')}")
    print()
    print("Files to remove:")
    print("  - docs/DATA_ORGANIZATION_PROTOCOL.md")
    print("  - docs/DOCS_ORGANIZATION_PROTOCOL.md")
    print("  - docs/ORGANIZATION_SUMMARY.md")


if __name__ == "__main__":
    main()
