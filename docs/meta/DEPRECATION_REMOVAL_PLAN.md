# Deprecation Removal Plan

**Date:** 2025-12-01  
**Status:** Planning Phase

---

## Overview

This document outlines the plan to remove deprecated fields and patterns from the codebase.

---

## Deprecated Items

### 1. `risk_score` Field (DEPRECATED → `attention_score`)

**Current Status:**
- ✅ Primary field: `attention_score` (used everywhere)
- ⚠️ Deprecated field: `risk_score` (kept for backward compatibility)
- **29 references** across 10 files still include `risk_score`

**Removal Plan:**

**Phase 1: Announcement (Week 1)**
- [ ] Add deprecation warnings in all responses
- [ ] Update all documentation to remove `risk_score` references
- [ ] Create migration guide for external integrations

**Phase 2: External Migration (Weeks 2-4)**
- [ ] Notify all known external integrations
- [ ] Provide migration scripts/examples
- [ ] Monitor usage via telemetry

**Phase 3: Code Removal (Week 5+)**
- [ ] Remove `risk_score` from all response dictionaries
- [ ] Remove backward compatibility code
- [ ] Update all internal references
- [ ] Remove from CSV exports

**Files to Update:**
- `src/governance_monitor.py` (2 references)
- `src/mcp_server_std.py` (9 references)
- `src/mcp_handlers/dialectic.py` (6 references)
- `src/mcp_handlers/core.py` (1 reference)
- `src/mcp_handlers/lifecycle.py` (1 reference)
- `src/mcp_handlers/observability.py` (2 references)
- `src/pattern_analysis.py` (1 reference)
- Documentation files (7 references)

**Estimated Effort:** 2-3 hours

---

### 2. `parameters` Array (DEPRECATED)

**Current Status:**
- ⚠️ Still accepted in API but not used in calculations
- **8 references** across 5 files

**Removal Plan:**

**Phase 1: Documentation (Week 1)**
- [ ] Update API documentation to mark as removed
- [ ] Add deprecation warnings in API responses

**Phase 2: Code Removal (Week 2)**
- [ ] Remove `parameters` from function signatures
- [ ] Remove from API schemas
- [ ] Remove from examples/documentation

**Files to Update:**
- `src/governance_monitor.py` (1 reference)
- `src/mcp_server_std.py` (2 references)
- `README.md` (3 references)
- `demos/gradio_demo.py` (1 reference)

**Estimated Effort:** 1-2 hours

---

## Timeline

**Total Timeline:** 5-6 weeks

**Week 1:** Announcement and documentation
**Weeks 2-4:** External migration period
**Week 5:** Code removal
**Week 6:** Testing and verification

---

## Risk Assessment

**Low Risk:**
- `parameters` - Already unused, minimal impact

**Medium Risk:**
- `risk_score` - Still used by some external integrations, needs migration period

**Mitigation:**
- Provide clear migration guides
- Maintain backward compatibility during transition
- Monitor telemetry for usage
- Provide deprecation warnings well in advance

---

## Success Criteria

- [ ] All deprecated fields removed from code
- [ ] All documentation updated
- [ ] No external integrations broken
- [ ] Test coverage maintained
- [ ] Migration guide available

---

## Notes

- Backward compatibility maintained during transition period
- External integrations will receive advance notice
- Deprecation warnings will be added before removal
- All changes will be documented in CHANGELOG.md

