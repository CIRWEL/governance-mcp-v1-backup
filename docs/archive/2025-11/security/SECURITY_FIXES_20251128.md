# Security Fixes - November 28, 2025
**Status:** ✅ Critical vulnerabilities fixed

---

## Vulnerabilities Fixed

### 1. ✅ RISK_REJECT_THRESHOLD Bug (Medium)
**Issue:** Code referenced non-existent `RISK_REJECT_THRESHOLD` constant  
**Fix:** Added `RISK_REJECT_THRESHOLD = 0.70` to `governance_config.py`  
**Impact:** Prevents crashes in edge cases (high complexity + high ethical drift)

---

### 2. ✅ API Key Retrieval Unprotected (High)
**Issue:** `get_agent_api_key` returned any agent's key without authentication  
**Attack:** Impersonation - get another agent's key and act as them  
**Fix:**
- Requires `api_key` parameter for existing agents
- Verifies authentication before returning key
- Regeneration requires auth + audit logging
- New agents can still get their own key (no auth needed)

**Location:** `src/mcp_handlers/lifecycle.py:handle_get_agent_api_key()`

---

### 3. ✅ Threshold Modification Unprotected (High)
**Issue:** `set_thresholds` allowed any agent to modify governance parameters  
**Attack:** Set `risk_approve_threshold` to 0.99 to bypass all checks  
**Fix:**
- Requires authentication (`agent_id` + `api_key`)
- Blocks threshold changes from critical/degraded agents
- Blocks threshold changes from high-risk agents (>0.60)
- Audit logging for all modification attempts
- Warning message in response

**Location:** `src/mcp_handlers/config.py:handle_set_thresholds()`

---

### 4. ✅ Knowledge Graph Poisoning (High)
**Issue:** Any agent could store malicious discoveries that get surfaced to new agents  
**Attack:** Inject fake "backdoor" discovery → new agents see it  
**Fix:**
- Filters discoveries from deleted/archived agents
- Basic keyword filtering for suspicious content
- Requires agent reputation (5+ updates) for suspicious keywords
- Validates source agent status before surfacing

**Location:** `src/mcp_handlers/core.py:handle_process_agent_update()`

**Remaining:** 
- ⚠️ Add rate limiting on `store_knowledge_graph`
- ⚠️ Add human review for high-severity discoveries
- ⚠️ Add reputation weighting (weight by agent health)

---

### 5. ✅ Error Message Leakage (Medium)
**Issue:** Error messages exposed internal structure (file paths, line numbers, stack traces)  
**Attack:** Probe edge cases to map codebase structure  
**Fix:**
- Sanitizes error messages (removes paths, line numbers, stack traces)
- Full tracebacks logged internally only
- Client-facing errors are sanitized
- Limits error message length (500 chars)

**Location:** `src/mcp_handlers/utils.py:error_response()` and `__init__.py:dispatch_tool()`

---

## Remaining Recommendations

### Medium Priority
1. **Rate limiting on knowledge storage** - Prevent spam/poisoning
2. **Reputation weighting** - Weight discoveries by agent health/history
3. **Human review** - Flag high-severity discoveries for review
4. **Clean up poison discovery** - Remove test "backdoor" discovery

### Low Priority
1. **Dialectic timeout** - Prevent bad-faith deadlock
2. **Ground truth prompts** - Auto-prompt humans for validation
3. **Self-reported input validation** - Derive complexity/confidence from behavior

---

## Testing Recommendations

1. **Test API key security:**
   - Try to get another agent's key without auth → Should fail
   - Try to regenerate another agent's key → Should fail

2. **Test threshold modification:**
   - Try to modify thresholds without auth → Should fail
   - Try to modify as critical agent → Should fail
   - Try to modify as high-risk agent → Should fail

3. **Test knowledge poisoning:**
   - Store discovery with "backdoor" keyword → Should be filtered for new agents
   - Store from new agent (<5 updates) → Should be filtered
   - Store from deleted agent → Should be filtered

4. **Test error sanitization:**
   - Trigger edge case error → Should not expose file paths/line numbers
   - Check server logs → Should have full traceback

---

**Status:** ✅ Critical vulnerabilities fixed  
**Next:** Implement remaining recommendations

