# Cleanup Opportunities - December 1, 2025

**Status:** Identified areas for improvement and cleanup

---

## Issues Found

### 1. `verdict_context` Not Returned in Response ⚠️

**Issue:** `verdict_context: 'aware'` is added to decision dict in `governance_monitor.py` but may not be passed through to the response.

**Location:** 
- Set in: `src/governance_monitor.py:856`
- Should appear in: `src/mcp_handlers/core.py` response

**Fix:** Ensure `verdict_context` is included in the response when present in decision dict.

---

### 2. "Degraded" Still in API Documentation 📝

**Issue:** Several places in `src/mcp_server_std.py` still reference "degraded" in docstrings/comments.

**Locations:**
- Line 1911: `"health": "healthy" | "degraded" | "unhealthy"`
- Line 2559: `"health_status": "healthy" | "degraded" | "critical" | "unknown"`
- Line 3375: `"degraded": 0,`

**Fix:** Update all docstrings to use "moderate" instead of "degraded" for consistency.

---

### 3. Duplicate Import 🔧

**Issue:** `import sys` appears twice in `src/mcp_handlers/core.py`.

**Location:** Lines 12 and 27

**Fix:** Remove duplicate import.

---

### 4. Inconsistent Status Enum Usage 📊

**Issue:** Enum value is `MODERATE` but some places still reference "degraded" in comments/docs.

**Status:** Mostly fixed, but some docstrings need updating.

---

## Recommended Fixes

### Priority 1 (High Impact)
1. ✅ Ensure `verdict_context` is returned in responses
2. ✅ Update API docstrings to remove "degraded" references

### Priority 2 (Cleanup)
3. ✅ Remove duplicate imports
4. ✅ Audit all docstrings for consistency

---

## Files to Update

1. `src/mcp_handlers/core.py` - Ensure verdict_context passed through, remove duplicate import
2. `src/mcp_server_std.py` - Update docstrings to use "moderate" not "degraded"

---

**Next Steps:** Apply fixes and verify all improvements are working.

