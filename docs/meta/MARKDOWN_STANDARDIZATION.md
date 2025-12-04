# Markdown Standardization Guide

**Purpose:** Create elegant, honest, and consistent documentation without feeling restrictive  
**Status:** Living document - evolves with the system  
**Last Updated:** 2025-12-01

---

## Philosophy

> **Standardize for clarity, not control. Make it easier to find and understand, not harder to create.**

This guide identifies inconsistencies and proposes elegant solutions. It's a **suggestion**, not a mandate. When in doubt, prioritize clarity and honesty over strict adherence.

---

## Current Inconsistencies Identified

### 1. Date Formats (Most Critical)

**Found patterns:**
- `November 26, 2025` (full month name)
- `2025-11-25` (ISO format)
- `Nov 29, 2025` (abbreviated month)
- `2025-12-01T10:30:00Z` (ISO with timestamp)

**Impact:** Confusing when searching, inconsistent appearance

**Recommendation:** Use ISO format (`YYYY-MM-DD`) for dates
- ✅ Sortable
- ✅ Unambiguous
- ✅ Machine-readable
- ✅ Consistent with codebase patterns

**Exception:** When readability matters more than sortability (e.g., "Created in November 2025"), use natural language.

---

### 2. Date Metadata Labels

**Found patterns:**
- `**Date:**` (most common)
- `**Last Updated:**` (common)
- `**Created:**` (less common)
- `**Updated:**` (rare)

**Impact:** Unclear which date is most relevant

**Recommendation:** 
- Use `**Last Updated:**` for living documents (guides, references)
- Use `**Date:**` for point-in-time documents (fixes, migrations, analysis)
- Use `**Created:**` only when creation date differs meaningfully from last update

**Format:** `**Last Updated:** YYYY-MM-DD` (ISO format)

---

### 3. Version Formats

**Found patterns:**
- `v2.0`
- `Version: 2.0`
- `v2.0.0`
- `Version: v2.0`

**Impact:** Inconsistent version references

**Recommendation:** Use `v2.0` format (no "Version:" label unless needed for clarity)
- ✅ Concise
- ✅ Consistent with semantic versioning
- ✅ Easy to grep

**When to include:** Only in guides that explain version differences or migration paths.

---

### 4. Link Formats

**Found patterns:**
- `[text](docs/guides/FILE.md)` (relative from root)
- `[text](/docs/guides/FILE.md)` (absolute)
- `[text](FILE.md)` (same directory)
- `[text](docs/reference/AI_ASSISTANT_GUIDE.md)` (full path)

**Impact:** Broken links when files move, inconsistent navigation

**Recommendation:** Use relative paths from document location
- ✅ Works regardless of where document is viewed
- ✅ Clearer intent
- ✅ Easier to refactor

**Examples:**
- From `docs/README.md` → `[Guide](guides/ONBOARDING.md)`
- From `docs/guides/ONBOARDING.md` → `[Reference](../reference/AI_ASSISTANT_GUIDE.md)`
- From root `README.md` → `[Guide](docs/guides/ONBOARDING.md)`

---

### 5. Header Metadata

**Found patterns:**
- Minimal: Just title
- Moderate: Title + date
- Extensive: Title + date + version + author + status

**Impact:** Some files feel over-documented, others under-documented

**Recommendation:** **Minimal header** (title only) for most documents
- ✅ Less cognitive load
- ✅ Focus on content
- ✅ Date/version tracked in git history

**Include metadata only when:**
- Document explains version differences → include version
- Document is time-sensitive → include date
- Document has specific author context → include author
- Document tracks status → include status

**Example minimal header:**
```markdown
# Document Title

Content starts here...
```

**Example when metadata needed:**
```markdown
# Migration Guide

**Version:** v2.0 → v3.0  
**Last Updated:** 2025-12-01

Migration content...
```

---

### 6. Emoji Usage

**Found patterns:**
- Heavy emoji usage (🚀 ✅ ⚠️ ❌)
- No emojis
- Selective emoji usage

**Impact:** Inconsistent tone, some find emojis distracting

**Recommendation:** **Use emojis sparingly** for visual scanning
- ✅ Helpful for quick reference (QUICK_REFERENCE.md)
- ✅ Useful for status indicators (✅ ⚠️ ❌)
- ❌ Avoid in technical reference docs
- ❌ Don't use as primary navigation

**Guideline:** If removing emojis doesn't hurt readability, remove them.

---

### 7. Section Separators

**Found patterns:**
- `---` (most common, correct)
- `***` (rare)
- No separator (some files)

**Impact:** Minor, but affects visual consistency

**Recommendation:** Use `---` for major section breaks
- ✅ Standard markdown
- ✅ Consistent visual rhythm
- ✅ Clear separation

**When to use:** Before major sections (not between every subsection)

---

### 8. Code Block Languages

**Found patterns:**
- `python` (most common)
- `bash` (common)
- `json` (common)
- No language specified (some)

**Impact:** Syntax highlighting inconsistent

**Recommendation:** Always specify language
- ✅ Better syntax highlighting
- ✅ Clearer intent
- ✅ Easier to read

---

### 9. Table Formatting

**Found patterns:**
- Standard markdown tables
- Some with inconsistent alignment
- Some with extra spacing

**Impact:** Minor readability issues

**Recommendation:** Use standard markdown tables with consistent alignment
```markdown
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Value 1  | Value 2  | Value 3  |
```

---

### 10. Attribution Patterns

**Found patterns:**
- `**Created by:** agent_name`
- `**Updated by:** agent_name`
- `Created: 2025-11-28 by agent_name`
- No attribution

**Impact:** Unclear authorship, some files feel over-attributed

**Recommendation:** **Don't include agent attribution** in headers
- ✅ Attribution tracked in git history
- ✅ Less noise in documents
- ✅ Focus on content, not authorship

**Exception:** When agent context matters (e.g., "Written by AI assistant after testing"), include in content, not header.

---

## Standardized Template

### For Guides and Reference Docs

```markdown
# Document Title

Brief one-line description if needed.

---

## Section 1

Content...

## Section 2

Content...

---

## Related Documentation

- [Link to related doc](path/to/doc.md)
- [Another link](path/to/another.md)
```

### For Fixes and Migrations

```markdown
# Fix/Migration Title

**Date:** YYYY-MM-DD

Description of what was fixed or migrated.

---

## Problem

What was wrong...

## Solution

What was done...

## Impact

What changed...
```

### For Analysis Documents

```markdown
# Analysis Title

**Date:** YYYY-MM-DD

Brief context if needed.

---

## Findings

Content...

## Recommendations

Content...
```

---

## Migration Strategy

### Phase 1: New Documents (Immediate)
- ✅ Apply standards to all new documents
- ✅ Use template above
- ✅ Minimal headers

### Phase 2: High-Traffic Documents (Gradual)
- Update `README.md`, `START_HERE.md`, `QUICK_REFERENCE.md`
- Fix date formats
- Standardize links
- Remove unnecessary metadata

### Phase 3: Archive Documents (Optional)
- Leave archived docs as-is (historical record)
- Only update if actively referenced

---

## Principles

1. **Clarity over consistency** - If breaking a rule improves clarity, break it
2. **Honesty over perfection** - Don't hide inconsistencies, acknowledge them
3. **Elegance over rigidity** - Standards should feel natural, not restrictive
4. **Progressive enhancement** - Better to have some consistency than none
5. **Context matters** - Different document types may need different standards

---

## Common Patterns to Avoid

### ❌ Over-Metadating
```markdown
# Document Title

**Created:** 2025-11-28
**Last Updated:** 2025-12-01
**Version:** v2.0
**Author:** agent_name
**Status:** Active
**Category:** Guide
**Tags:** documentation, standards

Content...
```

### ✅ Minimal Header
```markdown
# Document Title

Content...
```

---

### ❌ Inconsistent Dates
```markdown
**Date:** November 28, 2025
**Updated:** 2025-12-01
**Created:** Nov 29, 2025
```

### ✅ Consistent Dates
```markdown
**Last Updated:** 2025-12-01
```

---

### ❌ Broken Links
```markdown
[Guide](ONBOARDING.md)  # Breaks if file moves
[Guide](/docs/guides/ONBOARDING.md)  # Breaks if repo structure changes
```

### ✅ Relative Links
```markdown
[Guide](guides/ONBOARDING.md)  # From docs/README.md
[Guide](../guides/ONBOARDING.md)  # From docs/reference/
```

---

## Questions?

**Q: What if I'm not sure which standard to follow?**  
A: Use your best judgment. Clarity > consistency. This guide is a suggestion, not a mandate.

**Q: Should I update all existing documents?**  
A: No. Focus on new documents and high-traffic ones. Archive documents can stay as-is.

**Q: What about documents that don't fit the template?**  
A: Adapt the template. These are guidelines, not rules. Context matters.

**Q: How strict should I be?**  
A: Not very. The goal is elegance and honesty, not perfection. Some inconsistency is fine if it improves clarity.

---

## Summary

**Key Standards:**
1. Dates: ISO format (`YYYY-MM-DD`)
2. Links: Relative paths from document location
3. Headers: Minimal (title only, metadata only when needed)
4. Code blocks: Always specify language
5. Attribution: Don't include in headers (use git history)

**Key Principles:**
- Clarity over consistency
- Honesty over perfection
- Elegance over rigidity
- Progressive enhancement

**Remember:** These are suggestions to reduce confusion, not restrictions to limit creativity. When in doubt, prioritize clarity and honesty.

---

**This document itself follows these standards** - minimal header, ISO dates, relative links, clear structure.

