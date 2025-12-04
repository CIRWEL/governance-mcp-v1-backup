# Documentation Structure

This directory contains organized documentation for the UNITARES Governance Monitor system.

**Last Updated:** 2025-12-01  
**Total Files:** ~85 markdown files

**Organization Guide:** See [ORGANIZATION_GUIDE.md](ORGANIZATION_GUIDE.md) for complete organization standards.

## Directory Structure

### `/guides/` - User Guides (9 files)
Essential guides for using the system:
- `METRICS_GUIDE.md` - Understanding governance metrics
- `TROUBLESHOOTING.md` - Common issues and solutions
- `PARAMETER_EXAMPLES.md` - Parameter configuration examples
- `AGENT_ID_ARCHITECTURE.md` - Agent ID best practices
- `AUTHENTICATION.md` - Authentication guide
- `AUTHENTICATED_UPDATE_API.md` - API authentication
- `CLI_LOGGING_GUIDE.md` - CLI logging guide
- `KNOWLEDGE_LAYER_USAGE.md` - Knowledge layer usage
- `MCP_SETUP.md` - MCP server setup

### `/analysis/` - Analysis Documents (~9 files)
In-depth analysis and research documents:
- `COHERENCE_ANALYSIS.md` - Coherence threshold analysis & adaptive strategies
- `CROSS_MONITORING.md` - Cross-agent monitoring design and implementation
- `FIXES_AND_INCIDENTS.md` - Consolidated fixes and incident reports
- `INTEGRATION_STATUS.md` - Integration status and gap analysis
- `IP_AND_PUBLICATION_STRATEGY.md` - IP protection and GitHub publication strategy
- `MCP_CONCURRENCY_ARCHITECTURE.md` - MCP concurrency architecture
- `TEST_RESULTS.md` - Consolidated test results and verification
- `AUTHENTICATION_DESIGN.md` - Authentication design decisions
- `CLI_LOGGING_ARCHITECTURE.md` - CLI logging architecture

### `/archive/` - Historical Documentation
Historical status reports, bug fixes, and implementation notes:
- `/archive/` - Original archive files
- `/archive/sessions/` - Session summaries and agent experiences
- `/archive/consolidated/` - Consolidated historical docs (milestones, proposals, analysis)

### `/reference/` - Reference Documentation (4 files)
Reference materials and handoff documents:
- `CURSOR_HANDOFF.md` - Claude → Cursor handoff guide
- `README_FOR_FUTURE_CLAUDES.md` - Notes for future Claude instances
- `HOUSEKEEPING.md` - Housekeeping and maintenance notes
- `INTEGRATION_FLOW.md` - Integration flow documentation

## Root Documentation Files

**Protocols & Standards:**
- `ORGANIZATION_GUIDE.md` - Data and docs organization standards (single source of truth)
- `DOCUMENTATION_GUIDELINES.md` - When to use knowledge layer vs markdown

**Current Status:**
- `README.md` - This file (directory index)
- `QUICK_REFERENCE.md` - Quick reference guide
- `RELEASE_NOTES_v2.0.md` - Current release notes
- `SECURITY_AUDIT.md` - Security status

**Important Guides:**
- `BACKUP_STRATEGY.md` - Backup and recovery procedures
- `END_TO_END_FLOW.md` - End-to-end flow documentation
- `CONFIDENCE_GATING_AND_CALIBRATION.md` - Confidence gating documentation

**Note:** Some root-level files may need reorganization. See [ORGANIZATION_GUIDE.md](ORGANIZATION_GUIDE.md) for categorization guidelines.

## Project Root Documentation

- `README.md` - Main project documentation (root)
- `CHANGELOG.md` - Change log (root)
- `requirements-mcp.txt` - Python dependencies (root)

**Moved to organized locations:**
- `architecture/ARCHITECTURE.md` - System architecture
- `guides/ONBOARDING.md` - Onboarding guide
- `guides/USAGE_GUIDE.md` - Usage guide
- `reference/SYSTEM_SUMMARY.md` - System summary
- `archive/ARCHIVAL_SUMMARY_20251128.md` - Archival summary
- `archive/HARD_REMOVAL_SUMMARY_20251128.md` - Hard removal summary

---

## Organization Standards

**Organization Guide:** See [ORGANIZATION_GUIDE.md](ORGANIZATION_GUIDE.md) - Single source of truth for data and docs organization
**Documentation Guidelines:** See [DOCUMENTATION_GUIDELINES.md](DOCUMENTATION_GUIDELINES.md)

**Key Principles:**
- Use `store_knowledge` for discrete discoveries (bugs, insights, patterns)
- Use markdown files for comprehensive reports (1000+ words), guides, reference
- Organize by category: guides, reference, analysis, archive
- Archive docs >90 days old that are superseded

---

## Important Notices

**⚠️ Orchestrator Status (2025-11-29):**
The orchestrator (`src/orchestrator.py`) has been **ARCHIVED**. Do not use it. Instead:
- Use `process_agent_update` with `auto_export_on_significance: true` for significance-based logging
- Compose existing MCP tools directly for workflows (see tool documentation)
- See archived orchestrator code in `src/archive/orchestrator*.py` for reference only

## Recent Changes

**2025-11-29:**
- **Archived:** Orchestrator (over-engineered, good ideas extracted into proper implementations)
- **Added:** Significance-based auto-export to `process_agent_update` tool

**2025-11-27:**
- **Fixed:** Health status calculation bug (display mismatch resolved)
- **Fixed:** Loop detection gap (slow-stuck patterns now caught)
- **Updated:** MCP_CRITIQUE.md with latest fixes
- **Cleaned:** Archived redundant fix summaries

**2025-11-26:**
- **Fixed:** Consolidated 3 separate organization files into ONE unified guide (ORGANIZATION_GUIDE.md)
- **Fixed:** Removed hardcoded dates, now using dynamic date generation
- **Fixed:** Documented actual current structure instead of proposed future structure

**2025-11-25:**
- **Consolidated:** Related files merged (coherence, test results, fixes, etc.)
- **Archived:** Session summaries, milestones, proposals, historical analysis
- **Reduced:** From 107 to ~83 files (23% reduction)
- **Organized:** Better structure with clear separation of guides, analysis, and archive

