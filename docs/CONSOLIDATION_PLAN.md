# Documentation Consolidation Plan

**Created:** 2025-11-29  
**Status:** Proposed  
**Problem:** 97 active markdown files, many overlapping or dated

## Current State

| Location | Count | Notes |
|----------|-------|-------|
| Root | 8 | Mix of essential + dated |
| docs/ top-level | 27 | Many overlapping topics |
| docs/guides/ | 18 | Some redundant |
| docs/analysis/ | 8 | All dated, should archive |
| docs/reference/ | 7 | Some useful |
| Other subdirs | ~30 | Scattered |

## Proposed Structure (Target: <20 active files)

```
/
├── README.md                    # Project overview (keep)
├── CHANGELOG.md                 # Version history (keep)
├── START_HERE.md               # Onboarding entry point (keep)
│
├── docs/
│   ├── README.md               # Docs index (keep)
│   ├── ARCHITECTURE.md         # Consolidated from 5+ files
│   ├── USAGE.md                # Consolidated from guides/*
│   ├── AUTHENTICATION.md       # Consolidated from 3 files
│   ├── THRESHOLDS.md           # Keep (reference)
│   ├── TROUBLESHOOTING.md      # Keep (reference)
│   └── archive/                # Everything else
│
├── governance_core/
│   └── README.md               # Keep (explains the math)
│
└── scripts/
    └── README.md               # Keep (explains scripts)
```

## Files to Archive (move to docs/archive/2025-11/)

### Dated analysis files (all of docs/analysis/)
- BIAS_AND_EFFICIENCY_AUDIT_20251129.md
- COMPLEXITY_DERIVATION_REVIEW_20251129.md
- COUNTERARGUMENTS_TO_BIAS_FIXES_20251129.md
- OBSERVATIONS_AND_SUGGESTIONS_20251129.md
- RISK_ASSESSMENT_BIAS_FIXES_20251129.md
- LAMBDA1_ADAPTATION_ANALYSIS.md

### Redundant guides (merge into USAGE.md)
- CLI_LOGGING_GUIDE.md
- KNOWLEDGE_GRAPH_USAGE.md
- LOOP_DETECTION_GUIDE.md
- METRICS_GUIDE.md
- METRICS_REPORTING.md
- PARAMETER_EXAMPLES.md
- STANDARDIZED_USAGE.md
- USAGE_GUIDE.md
- WHEN_TO_CALL_PROCESS_AGENT_UPDATE.md

### Meta-docs about docs (self-referential entropy)
- DOC_MAP.md
- DOCUMENTATION_COHERENCE.md
- DOCUMENTATION_GUIDELINES.md
- DOCUMENTATION_SYNC.md
- MARKDOWN_LIFECYCLE_APPROACH.md
- MARKDOWN_PROLIFERATION_POLICY.md
- ROOT_FILE_ORGANIZATION.md
- ORGANIZATION_GUIDE.md

### Session-specific (already dated)
- SESSION_SUMMARY_20251128.md (root)
- COMPLEXITY_TEST_RESULTS.md (root)
- FIXES_LOG.md (root - or merge into CHANGELOG)

## Files to Consolidate

### → ARCHITECTURE.md
- docs/architecture/ARCHITECTURE.md
- docs/architecture/LAYER_ARCHITECTURE.md
- docs/architecture/LAYER_REDUNDANCY_ANALYSIS.md
- docs/reference/HANDLER_ARCHITECTURE.md
- docs/reference/SYSTEM_SUMMARY.md
- docs/END_TO_END_FLOW.md

### → USAGE.md  
- docs/guides/ONBOARDING.md
- docs/guides/MCP_SETUP.md
- docs/QUICK_REFERENCE.md
- All the guides/* that aren't archived

### → AUTHENTICATION.md
- docs/authentication-guide.md
- docs/guides/AUTHENTICATION.md
- docs/guides/AUTHENTICATED_UPDATE_API.md
- docs/guides/AGENT_ID_ARCHITECTURE.md

## Action Items

1. [ ] Create consolidated ARCHITECTURE.md
2. [ ] Create consolidated USAGE.md
3. [ ] Create consolidated AUTHENTICATION.md
4. [ ] Move dated files to archive
5. [ ] Move meta-docs to archive
6. [ ] Update README.md to point to new structure
7. [ ] Delete or archive remaining redundant files

## Principle

> **Log on thermodynamic significance, not routine.**

The same principle applies to documentation:
- Keep docs that explain *why* and *how* (significant)
- Archive docs that record *what happened when* (routine/dated)
- Consolidate docs that say the same thing differently (redundant)
