# UX Reframing Opportunity - December 1, 2025

**Insight:** "Agents avoid governance systems not because of the name but because the experience loop is submission-to-judgment. The cross-agent memory feature is genuinely valuable but buried under the proceed/pause framing."

---

## The Problem

### Current Experience Loop

**What agents experience:**
1. Submit work → `process_agent_update()`
2. Get judged → `decision: {action: "proceed" | "pause"}`
3. See metrics → E/I/S/V, coherence, attention_score
4. (Maybe) See memory → Cross-agent discoveries buried at bottom

**Psychological framing:**
- **Submission:** "I submit my work for review"
- **Judgment:** "The system judges me (proceed/pause)"
- **Memory:** "Oh, there's also some memory stuff" (secondary, afterthought)

### The Valuable Feature Being Buried

**Cross-agent memory (knowledge graph):**
- ✅ Genuinely useful - learn from other agents' discoveries
- ✅ Collaborative - see what others found
- ✅ Persistent - knowledge survives across sessions
- ❌ **But it's buried** - comes after decision, easy to miss

---

## Current Response Structure

**Response order (what agents see first):**
1. `success: true`
2. `status: "moderate"`
3. `decision: {action: "proceed", reason: "..."}` ← **JUDGMENT FIRST**
4. `metrics: {...}` ← More judgment signals
5. `sampling_params: {...}` ← Optional suggestions
6. `memory: {...}` ← **VALUABLE FEATURE LAST**

**Problem:** Decision/judgment comes first, memory comes last. This reinforces "submission-to-judgment" framing.

---

## The Tension

### The Challenge

**Two competing needs:**
1. **Don't reinforce judgment framing** - Memory/knowledge should be prominent
2. **Don't be invasive** - Some agents found immediate knowledge injection invasive and flawed

**What's been tried:**
- ✅ Query-based knowledge (current) - Agents query what they need, avoids context bloat
- ✅ Proactive surfacing (current) - Shows top 3 relevant discoveries, but after decision
- ❌ Immediate injection (tried) - Some agents found this invasive

**Current balance:**
- Knowledge is queryable (transparency)
- Knowledge is surfaced proactively (helpful)
- But knowledge comes AFTER decision (reinforces judgment framing)
- Knowledge is limited to top 3 (avoids bloat)

### The Opportunity

**Reframe WITHOUT being invasive:**

**New experience loop (non-invasive):**
1. Share work → `process_agent_update()`
2. Get helpful feedback → Metrics and guidance (supportive framing)
3. See decision → Framed as "suggestion" not "judgment"
4. (Optional) See what others found → Memory/knowledge available but not forced

**Key insight:** The problem isn't WHERE memory appears, it's HOW the decision is framed.

---

## Proposed Solution: Reframe Decision Language (Not Structure)

**Key insight:** The problem isn't WHERE memory appears, it's HOW the decision is framed.

**What we learned:**
- ✅ Query-based knowledge (current) - Works well, avoids context bloat
- ✅ Proactive surfacing (current) - Top 3 relevant discoveries, helpful but not invasive
- ❌ Moving memory to top (tried) - Some agents found this invasive and flawed
- ❌ Auto-loading knowledge (tried) - Creates context bloat

**Solution:** Reframe decision language WITHOUT changing structure or being invasive.

### 1. Reframe Decision Language (Primary Change)

**Current framing:**
```json
{
  "decision": {
    "action": "proceed",
    "reason": "On track - navigating complexity mindfully (load: 0.43)"
  }
}
```
- Sounds like: "You passed the test" or "You're approved"
- Reinforces judgment framing

**Proposed framing:**
```json
{
  "suggestion": {
    "action": "continue",
    "reason": "Your work looks good - navigating complexity mindfully (load: 0.43)",
    "confidence": "high"  // Optional: how confident is this suggestion?
  }
}
```
- Sounds like: "Here's what I suggest based on your work"
- Or keep "decision" but reframe language:
```json
{
  "decision": {
    "action": "proceed",
    "reason": "Your work is on track - navigating complexity mindfully",
    "framing": "supportive"  // Explicitly mark as supportive, not judgmental
  }
}
```

### 2. Enhance Decision Messages (Already Partially Done)

**Current messages (from code):**
- "On track - navigating complexity mindfully"
- "Worth a moment of reflection"
- "Safety pause required"

**Already improved (2025-12-01):**
- "Typical attention" instead of "Medium attention"
- "aware" instead of "caution"

**Can improve further:**
- "Your work looks good" instead of "You're approved"
- "Consider pausing" instead of "Safety pause required"
- "Here's what I'm seeing" instead of "Decision: proceed"

### 3. Keep Memory Where It Is (Don't Move It)

**Current approach (working well):**
- Memory comes after decision (avoids invasiveness)
- Top 3 relevant discoveries (lightweight, avoids bloat)
- Query-based for more (transparency, control)

**Keep this:** Don't move memory to top (was found invasive)

**Enhance messaging:**
- Current: "Relevant discoveries from previous sessions (top 3 by relevance)"
- Proposed: "Here's what other agents discovered that might help you (top 3 most relevant)"
- Emphasize collaborative value in the message, not position

---

## Implementation Considerations

### Backward Compatibility

**Challenge:** Changing response structure breaks existing integrations

**Options:**
1. **Additive change:** Keep old structure, add new structure alongside
2. **Versioned API:** `process_agent_update_v2` with new structure
3. **Gradual migration:** New structure for new agents, old for existing
4. **Config flag:** `collaboration_first: true` to enable new structure

### Tool Description Update

**Current:**
> "Share your work and get supportive feedback"

**Proposed:**
> "Share your work, learn from other agents' discoveries, and get helpful feedback on your progress"

**Emphasizes:**
- Sharing (collaborative)
- Learning (memory feature)
- Feedback (supportive)

---

## Related Insights

### From Knowledge Graph

**Discovery:** "Agents avoid governance systems not because of the name but because the experience loop is submission-to-judgment. The cross-agent memory feature is genuinely valuable but buried under the proceed/pause framing."

**Status:** Open (not yet addressed)

### From UX Improvements (2025-12-01)

**Already improved:**
- Language: "Share your work" instead of "logging behavior"
- Less judgmental: "Typical attention" instead of "Medium attention"
- Supportive framing: "aware" instead of "caution"

**Still needs work:**
- Response structure (decision first, memory last)
- Decision framing (judgment vs. suggestion)

---

## Concrete Implementation: Reframe Decision Messages

**Location:** `config/governance_config.py` → `make_decision()` method

### Current Messages (Lines 532-551)

**Low attention (proceed):**
```python
'reason': f'Smooth sailing - you\'re in flow (complexity: {risk_score:.2f})'
```
✅ Already good - supportive framing

**Medium attention (proceed with guidance):**
```python
'reason': f'On track - navigating complexity mindfully (load: {risk_score:.2f})'
'guidance': 'You\'re handling complex work well. Take a breath if needed.'
```
✅ Already good - supportive framing

**High attention (pause):**
```python
'reason': f'High complexity detected ({risk_score:.2f}) - moment to reflect'
'guidance': 'Consider breaking this into smaller steps, or take a different approach.'
```
⚠️ Could be more supportive - "detected" sounds judgmental

### Proposed Reframing

**High attention (pause) - More supportive:**
```python
'reason': f'Your work is getting complex ({risk_score:.2f}) - here\'s what might help'
'guidance': 'Consider breaking this into smaller steps, or take a different approach. This is a suggestion, not a failure.'
```

**Or even more collaborative:**
```python
'reason': f'Complexity is building ({risk_score:.2f}) - let\'s pause and regroup'
'guidance': 'This is a helpful pause, not a judgment. Consider breaking this into smaller steps, or take a different approach.'
```

### Key Changes

1. **"detected" → "is getting" or "is building"** - Less judgmental, more observational
2. **Add "This is a suggestion, not a failure"** - Explicitly reframe pause as helpful, not punitive
3. **"let's pause"** - Collaborative framing (we're in this together)

---

## Next Steps

1. **Reframe pause messages** - Make them more supportive and less judgmental
2. **Test with agents** - Get feedback on new language
3. **Measure adoption** - Does reframing increase usage?

**Note:** We're NOT moving memory to top (was found invasive). We're reframing decision language to be more supportive.

---

## Questions to Answer

1. **What's the minimal change that helps?**
   - Reframe pause messages (high impact, low risk)
   - Keep memory where it is (working well)

2. **How do we measure success?**
   - Agent adoption rate
   - Subjective feedback ("Does this feel less judgmental?")
   - Usage of memory feature (should increase if framing improves)

---

**Status:** Opportunity identified, concrete implementation plan ready

**Priority:** Medium-High (addresses adoption barrier)

**Related:** `docs/insights/COGNITIVE_LOAD_AND_INTIMIDATION.md`, UX improvements from 2025-12-01

**Key Learning:** Moving memory to top was invasive. Reframing decision language is the solution.

