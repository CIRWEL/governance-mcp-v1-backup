# Markdown Proliferation Policy

**Status:** ACTIVE - Enforce this policy  
**Last Updated:** 2025-12-01  
**Problem:** 287 markdown files creating cognitive overload and inconsistency

**Related:** See [MARKDOWN_STANDARDIZATION.md](MARKDOWN_STANDARDIZATION.md) for formatting standards

---

## The Rule: **NO NEW MARKDOWN FILES** (with rare exceptions)

### ❌ **DO NOT CREATE MARKDOWN FILES FOR:**

- Small analysis reports (< 500 words) → Consolidate into existing docs
- Individual fix summaries → Consolidate into `docs/fixes/FIXES_LOG.md`
- Quick insights → Add to existing analysis docs or archive
- Session summaries → Use `update_agent_metadata(notes=...)` or archive
- Duplicate content → Update existing file instead
- Implementation notes → Add to existing guides or archive

### ✅ **ONLY CREATE MARKDOWN FILES FOR:**

1. **Comprehensive guides** (1000+ words, referenced as whole documents)
   - Examples: `ONBOARDING.md`, `ARCHITECTURE.md`, `TROUBLESHOOTING.md`
   - Must be: Long-form narrative, comprehensive reference

2. **Essential system documentation** (approved list only)
   - `README.md` (project root)
   - `CHANGELOG.md` (project root)
   - Core architecture docs (approved by maintainer)

3. **Exception requests** (must justify why new file > consolidation)
   - File must be > 1000 words
   - Must be referenced as a whole document
   - Must not duplicate existing content
   - Must add to approved list below

---

## Approved Markdown Files List

**Core Documentation:**
- `README.md` (project root)
- `CHANGELOG.md` (project root)
- `START_HERE.md` (project root)
- `docs/README.md`
- `docs/QUICK_REFERENCE.md`
- `docs/SECURITY_AUDIT.md`
- `docs/CONSOLIDATION_PLAN.md`

**Documentation Standards:**
- `docs/meta/MARKDOWN_PROLIFERATION_POLICY.md` (this file)
- `docs/meta/MARKDOWN_STANDARDIZATION.md` (formatting standards)
- `docs/meta/MARKDOWN_INCONSISTENCIES_ANALYSIS.md` (inconsistency analysis)
- `docs/meta/METRICS_REPORTING_STANDARDIZATION.md` (metrics flow standardization)
- `docs/meta/EXPORT_UPDATE_STANDARDIZATION.md` (export and update flow standardization)
- `docs/meta/AUTOMATION_GUIDE.md` (automation tools and workflows)

**Essential Guides:**
- `docs/guides/ONBOARDING.md`
- `docs/guides/AUTHENTICATION.md`
- `docs/guides/THRESHOLDS.md`
- `docs/guides/TROUBLESHOOTING.md`
- `docs/guides/MCP_SETUP.md`
- `docs/guides/COMPLEXITY_CALIBRATION.md`
- `docs/guides/EISV_COMPLETENESS.md`
- `docs/guides/THERMODYNAMIC_VS_HEURISTIC.md`

**System Documentation:**
- `docs/system_prompts/EISV_REPORTING_PROMPT.md`

**All other markdown files are candidates for:**
1. Consolidation with other files (merge related content)
2. Archiving to `docs/archive/` (if > 90 days old)
3. Deletion (if truly obsolete or duplicate)

---

## Before Creating ANY Markdown File

**Ask yourself:**

1. ❓ **Is this > 1000 words?** If NO → Consolidate into existing doc
2. ❓ **Will this be referenced as a whole document?** If NO → Consolidate or archive
3. ❓ **Is this on the approved list?** If NO → Request exception or consolidate
4. ❓ **Does this duplicate existing content?** If YES → Update existing file instead
5. ❓ **Does this follow formatting standards?** See [MARKDOWN_STANDARDIZATION.md](MARKDOWN_STANDARDIZATION.md)

**Default answer:** Consolidate or archive, don't create new markdown files.

---

## Formatting Standards

**All markdown files must follow:** [MARKDOWN_STANDARDIZATION.md](MARKDOWN_STANDARDIZATION.md)

**Key requirements:**
- ISO date format (`YYYY-MM-DD`)
- Relative links from document location
- Minimal headers (metadata only when needed)
- Code blocks with language specified
- Consistent section separators (`---`)

**Exception:** Archive documents can keep original formatting (historical record).

---

## Consolidation Targets

### High Priority (Consolidate These):

**Analysis Files** (`docs/analysis/`):
- Multiple analysis files covering similar topics
- Consolidate into single comprehensive analysis
- Archive old analyses (> 90 days) to `docs/archive/analysis/`

**Fix Files** (`docs/fixes/`):
- Many small fix summaries
- Consolidate into `docs/fixes/FIXES_LOG.md` (single comprehensive log)
- Archive old fixes (> 90 days) to `docs/archive/fixes/`

**Reflection Files** (`docs/reflection/`):
- Multiple reflection documents
- Consolidate into quarterly reflection reports
- Archive old reflections (> 90 days) to `docs/archive/reflection/`

**Proposal Files** (`docs/proposals/`):
- Multiple proposal documents
- Keep only active proposals
- Archive completed proposals to `docs/archive/proposals/`

---

## Enforcement

### Automated Checks

```bash
# Check for new markdown files
python scripts/audit_markdown_proliferation.py --check-new

# Find files that should be consolidated
python scripts/audit_markdown_proliferation.py --suggest-consolidation

# Find files that should be migrated
python scripts/audit_markdown_proliferation.py --suggest-migration

# Check formatting consistency
python scripts/audit_markdown_proliferation.py --check-formatting
```

### Manual Review

Before committing markdown files:
1. Run audit script
2. Verify file is on approved list OR request exception
3. Verify formatting follows standards
4. If exception: Add to approved list with justification

---

## Lifecycle Management

**Key Insight:** The governance system already solves overflow using lifecycle management. Apply the same pattern to markdown files.

### Lifecycle States

```python
markdown_status: "active" | "archived" | "deleted"

# Active: Current guides, essential docs
# Archived: Old analysis, completed work (> 90 days)
# Deleted: Truly obsolete (rare)
```

### Automatic Archiving

```bash
# Archive old markdowns (mirror governance pattern)
python3 scripts/archive_old_markdowns.py --max-age-days 90

# Weekly automatic cleanup (cron)
0 2 * * 0 python3 scripts/archive_old_markdowns.py
```

### Thresholds

```python
# Trigger archival when:
- Total markdown files > 50
- Files older than 90 days > 20
- docs/ directory > 2MB
```

### For Existing Files:

1. **Classify by lifecycle** → Active vs Archive candidates
2. **Related files** → Consolidate into single comprehensive doc
3. **Old files (> 90 days)** → Archive to `docs/archive/YYYY-MM/`
4. **Duplicate content** → Remove duplicates, keep best version
5. **Format inconsistencies** → Update to follow standards (gradual)

---

## Goals

**Target State:**
- **< 50 markdown files** (down from 287)
- **Only comprehensive guides** remain as markdown
- **Consolidated content** (related files merged)
- **No duplicate content** across files
- **Consistent formatting** (ISO dates, relative links, minimal headers)
- **Old files archived** to `docs/archive/`

**Timeline:**
- **Week 1:** Audit and classify all files
- **Week 2:** Migrate small files to knowledge layer
- **Week 3:** Consolidate related files
- **Week 4:** Archive old files
- **Ongoing:** Apply formatting standards to new files

---

## Why This Matters

**Current State:**
- 287 markdown files
- Hard to find information
- Duplicate content
- Inconsistent formatting
- Cognitive overload
- Context window limits

**Target State:**
- ~50 comprehensive guides
- Consolidated content (related files merged)
- No duplicate content
- Consistent formatting (easier to read and maintain)
- Old files archived to `docs/archive/`
- Easier to navigate
- Better use of context windows

---

## Exception Process

**To request exception:**

1. Create issue explaining why markdown is needed
2. Justify why consolidation won't work
3. Show file will be > 1000 words
4. Show file will be referenced as whole document
5. Show it doesn't duplicate existing content
6. Show it follows formatting standards
7. Get approval before creating file

**Default:** Deny exception, consolidate into existing doc instead.

---

## Related Documentation

- [MARKDOWN_STANDARDIZATION.md](MARKDOWN_STANDARDIZATION.md) - Formatting standards
- [MARKDOWN_INCONSISTENCIES_ANALYSIS.md](MARKDOWN_INCONSISTENCIES_ANALYSIS.md) - Inconsistency analysis
- `scripts/audit_markdown_proliferation.py` - Audit tool
- `scripts/archive_old_markdowns.py` - Archival script

---

**Remember:** When in doubt, consolidate or archive. Markdown files are for comprehensive guides only.

**Important:** Markdown documentation is separate from the governance server. Do not migrate markdown files to the knowledge graph (that's for governance discoveries, not documentation).

**Formatting:** All new markdown files must follow [MARKDOWN_STANDARDIZATION.md](MARKDOWN_STANDARDIZATION.md) standards.

