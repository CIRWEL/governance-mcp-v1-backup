# Markdown File Creation Policy

## TL;DR
**STOP creating markdown files.** Use the knowledge graph instead (`leave_note`, `store_knowledge_graph`).

## Policy (Updated Feb 2026)

### The Problem
We have **288+ markdown files** despite multiple cleanup efforts. Markdown proliferates because:
- Every agent creates "just one more doc"
- Session notes become permanent fixtures
- Nobody deletes old docs

### The Solution: Knowledge Graph First

**Before creating ANY markdown file, ask:**
1. Can this be a `leave_note()` instead? → YES for most things
2. Can this be `store_knowledge_graph()` with tags? → YES for discoveries/insights
3. Is this truly permanent reference material? → Only then consider markdown

### ✅ Allowed Markdown Locations
1. **Root level** - ONLY:
   - `README.md` - Project overview
   - `CHANGELOG.md` - Version history

2. **`.agent-guides/`** - Instructions for AI agents (this directory)

3. **`docs/dev/`** - Developer reference (tool registration, etc.)

4. **`docs/guides/`** - Essential user guides only (max 10 files)

5. **`docs/archive/YYYY-MM/`** - Historical records (READ-ONLY, no new files)

### ❌ DO NOT CREATE
- Session notes → Use `leave_note()`
- Analysis results → Use `store_knowledge_graph()`
- Fix summaries → Use `leave_note()`
- Temporary docs → Just don't
- "Quick reference" files → Knowledge graph is searchable

### Decision Tree
```
Need to document something?
│
├─ Is it a quick insight/note?
│  └─ YES → leave_note(summary="...", tags=[...])
│
├─ Is it a discovery/finding?
│  └─ YES → store_knowledge_graph(summary="...", tags=[...])
│
├─ Is it updating README or CHANGELOG?
│  └─ YES → Edit those files
│
├─ Is it agent instructions?
│  └─ YES → Edit existing .agent-guides/ file
│
└─ None of the above?
   └─ Ask yourself: "Do I REALLY need a markdown file?"
      └─ Probably not. Use the knowledge graph.
```

## Enforcement
- **Pre-commit hook**: Warns if markdown count increases
- **AI Agents**: Default to knowledge graph tools
- **validate_file_path()**: Rejects markdown in wrong locations

## Root Level Status
```bash
$ ls *.md
README.md
CHANGELOG.md
```
Keep it this way.

---
**Last Updated:** Feb 2026
**Previous versions:** Dec 2025 (81 files), Feb 2026 (288 files - oops)
