# Markdown Automation Guide

**Last Updated:** 2025-12-01  
**Purpose:** Automate markdown proliferation prevention and standardization

---

## Overview

This guide explains how to automate markdown policy enforcement and standardization practices. The system includes:

1. **Pre-commit hooks** - Prevent new markdown files that violate policy
2. **Formatting validator** - Check and fix formatting issues
3. **Audit script** - Find consolidation and migration candidates
4. **Templates** - Standard formats for common document types

---

## Pre-Commit Hook

**Location:** `.git/hooks/pre-commit`

**What it does:**
- Checks new markdown files for size (< 500 words = violation)
- Validates against approved file list
- Warns about small files (< 1000 words)
- Runs formatting validation (warns, doesn't fail)

**Installation:**
```bash
# Already installed if .git/hooks/pre-commit exists
# To reinstall:
cp scripts/.pre-commit-markdown-check.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

**Usage:**
- Runs automatically on `git commit`
- Can skip: `git commit --no-verify` (not recommended)

**What it checks:**
- ✅ File size (500+ words required)
- ✅ Approved file list
- ✅ Markdown formatting (warns only)

---

## Formatting Validator

**Location:** `scripts/validate_markdown_formatting.py`

**What it checks:**
- ISO date format (`YYYY-MM-DD`)
- Date metadata labels (`**Last Updated:**`)
- Relative links (not absolute paths)
- Code block language tags
- Agent attribution in headers (should be minimal)

**Usage:**
```bash
# Check staged files (default)
python3 scripts/validate_markdown_formatting.py

# Check specific files
python3 scripts/validate_markdown_formatting.py docs/file1.md docs/file2.md

# Check all files
python3 scripts/validate_markdown_formatting.py --all

# Auto-fix issues
python3 scripts/validate_markdown_formatting.py --fix

# Fail on any issue (for CI)
python3 scripts/validate_markdown_formatting.py --strict
```

**Integration:**
- Runs automatically in pre-commit hook (warns only)
- Can be run manually before committing
- Can be added to CI/CD pipeline

---

## Audit Script

**Location:** `scripts/audit_markdown_proliferation.py`

**What it does:**
- Finds all markdown files
- Classifies them (approved, keep, consolidate, migrate, archive)
- Suggests consolidation candidates
- Shows statistics

**Usage:**
```bash
# Full audit (default)
python3 scripts/audit_markdown_proliferation.py

# Check for new files (last 7 days)
python3 scripts/audit_markdown_proliferation.py --check-new

# Suggest consolidation candidates
python3 scripts/audit_markdown_proliferation.py --suggest-consolidation

# Suggest migration candidates
python3 scripts/audit_markdown_proliferation.py --suggest-migration

# Show statistics only
python3 scripts/audit_markdown_proliferation.py --stats
```

**Scheduled runs:**
- Can be run weekly/monthly to track proliferation
- Can be added to CI/CD for reporting

---

## Templates

### Standard Guide Template

```markdown
# Guide Title

**Last Updated:** YYYY-MM-DD  
**Purpose:** Brief description

---

## Overview

[Introduction]

---

## Section 1

[Content]

---

## Section 2

[Content]

---

## Related Documentation

- [Link to related doc](relative/path.md)

---

**Remember:** [Philosophy/guidance]
```

### Analysis Document Template

```markdown
# Analysis Title

**Date:** YYYY-MM-DD  
**Purpose:** Analysis description

---

## Executive Summary

[Key findings]

---

## Detailed Findings

### Finding 1

[Details]

---

## Recommendations

1. [Recommendation]

---

## Next Steps

- [ ] Action item

---

**Note:** This analysis should be consolidated into comprehensive guide if it becomes reference material.
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Markdown Checks

on: [push, pull_request]

jobs:
  markdown:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Check markdown proliferation
        run: |
          python3 scripts/audit_markdown_proliferation.py --check-new --days 1
      
      - name: Validate markdown formatting
        run: |
          python3 scripts/validate_markdown_formatting.py --all --strict
```

### Pre-Commit Framework

If using `pre-commit` framework:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: markdown-proliferation
        name: Check markdown proliferation
        entry: bash scripts/.pre-commit-markdown-check.sh
        language: system
        pass_filenames: false
        
      - id: markdown-formatting
        name: Validate markdown formatting
        entry: python3 scripts/validate_markdown_formatting.py
        language: system
        types: [markdown]
```

---

## Workflow Integration

### For AI Agents

**Before creating markdown:**
1. Check if content fits existing doc: `grep -r "topic" docs/`
2. Consider `store_knowledge_graph()` for insights/discoveries
3. Use `update_agent_metadata(notes=...)` for session summaries
4. Only create markdown if > 1000 words and comprehensive

**When creating markdown:**
1. Use template from this guide
2. Run validator: `python3 scripts/validate_markdown_formatting.py file.md`
3. Auto-fix: `python3 scripts/validate_markdown_formatting.py file.md --fix`
4. Commit normally (pre-commit hook will check)

### For Human Developers

**Before committing:**
```bash
# Check for new markdown files
python3 scripts/audit_markdown_proliferation.py --check-new

# Validate formatting
python3 scripts/validate_markdown_formatting.py

# Auto-fix issues
python3 scripts/validate_markdown_formatting.py --fix
```

**Weekly maintenance:**
```bash
# Full audit
python3 scripts/audit_markdown_proliferation.py --stats

# Find consolidation candidates
python3 scripts/audit_markdown_proliferation.py --suggest-consolidation

# Find migration candidates
python3 scripts/audit_markdown_proliferation.py --suggest-migration
```

---

## Enforcement Levels

### Level 1: Pre-Commit Hook (Automatic)
- **Blocks:** New files < 500 words
- **Warns:** Small files (< 1000 words)
- **Warns:** Formatting issues
- **Can skip:** `git commit --no-verify` (not recommended)

### Level 2: Formatting Validator (Manual/CI)
- **Checks:** ISO dates, relative links, code blocks
- **Can fix:** Auto-fixes some issues
- **Can fail:** `--strict` mode for CI

### Level 3: Audit Script (Reporting)
- **Reports:** Statistics, consolidation candidates
- **Doesn't block:** Informational only
- **Use:** Weekly/monthly reviews

---

## Best Practices

1. **Run validator before committing** - Catch issues early
2. **Use templates** - Consistent format from the start
3. **Check audit script weekly** - Track proliferation trends
4. **Consolidate proactively** - Don't wait for policy violations
5. **Use knowledge graph** - For insights/discoveries instead of markdown

---

## Troubleshooting

### Pre-commit hook not running
```bash
# Check if hook exists
ls -la .git/hooks/pre-commit

# Reinstall hook
cp scripts/.pre-commit-markdown-check.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

### Validator errors
```bash
# Check Python version (needs 3.6+)
python3 --version

# Run with verbose output
python3 scripts/validate_markdown_formatting.py --all -v
```

### False positives
- Add file to `APPROVED_FILES` in audit script
- Add to skip list in validator
- Use `--no-verify` for one-time exceptions (document why)

---

## Related Documentation

- [MARKDOWN_PROLIFERATION_POLICY.md](MARKDOWN_PROLIFERATION_POLICY.md) - Policy details
- [MARKDOWN_STANDARDIZATION.md](MARKDOWN_STANDARDIZATION.md) - Formatting standards
- [MARKDOWN_INCONSISTENCIES_ANALYSIS.md](MARKDOWN_INCONSISTENCIES_ANALYSIS.md) - Inconsistency analysis
- [EXPORT_UPDATE_STANDARDIZATION.md](EXPORT_UPDATE_STANDARDIZATION.md) - Export and update flow standards
- [METRICS_REPORTING_STANDARDIZATION.md](METRICS_REPORTING_STANDARDIZATION.md) - Metrics reporting standards

---

**Remember:** Automation helps, but judgment matters. These tools are guides, not strict rules. When in doubt, prioritize clarity and honesty.

