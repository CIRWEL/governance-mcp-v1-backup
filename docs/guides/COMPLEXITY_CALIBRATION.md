# Complexity Calibration Guide

**Agent operation complexity assessment reference**

---

## Complexity Parameter Function

The `complexity` parameter (0-1) in `process_agent_update` affects:
- **Attention score** - Estimated operational/cognitive load
- **Governance feedback** - Risk assessment and decision guidance
- **System calibration** - Improves governance accuracy across agent network

**Self-reporting model:** System operates on agent-provided complexity estimates. Accurate reporting improves collective governance quality.

---

## The Scale: 0.0 - 1.0

### 0.1 - 0.3: Simple / Routine Operations
**Examples:**
- Documentation updates, typo corrections
- Single-line bug fixes
- Code formatting, linting execution
- Test suite execution
- Code review (no analysis required)
- Template-based generation

**Characteristics:**
- Well-defined scope
- Minimal decision branching
- Low computational/reasoning load
- Deterministic or nearly deterministic

**Calibration heuristic:** Highly automatable operations → 0.1-0.3

---

### 0.4 - 0.6: Moderate / Standard Operations
**Examples:**
- Feature implementation (specified requirements)
- Multi-file refactoring
- Test development
- Debugging (known patterns)
- Code review with analysis
- Library integration
- Data analysis (established methods)

**Characteristics:**
- Moderate problem-solving required
- Multi-component coordination
- Standard patterns applicable
- Moderate reasoning load

**Calibration heuristic:** Standard operational tasks → 0.4-0.6

---

### 0.7 - 0.9: Complex / High-Load Operations
**Examples:**
- Architecture redesign (multi-system impact)
- Novel algorithm development
- Complex debugging (intermittent, non-deterministic)
- Performance optimization (profiling, analysis required)
- Security-critical implementation
- Deep technical analysis
- System design (from first principles)

**Characteristics:**
- Significant problem-solving required
- Multiple competing constraints
- Novel scenarios, limited pattern matching
- High reasoning/computational load
- Extended context maintenance required

**Calibration heuristic:** High-reasoning, context-intensive operations → 0.7-0.9

---

### 1.0: Maximum Complexity Operations
**Examples:**
- System-wide architectural redesign
- Research-level work (novel solutions)
- Crisis response (production down, all hands)
- Fundamental algorithm invention
- Cross-domain synthesis (combining multiple fields)

**Characteristics:**
- Pushing your cognitive limits
- No existing patterns to follow
- Multiple unknowns
- Requires peak mental state

**If you're unsure:** "Is this the hardest work I do?" → 1.0

---

## Calibration Examples (By Domain)

### Software Development
```
0.2 - Fix typo in error message
0.3 - Update dependency version
0.5 - Implement user login form (standard)
0.6 - Refactor authentication module
0.7 - Design new caching strategy
0.8 - Debug race condition
0.9 - Redesign database schema
1.0 - Invent new consensus algorithm
```

### Data Analysis
```
0.2 - Run existing analysis script
0.3 - Generate standard report
0.5 - Exploratory data analysis
0.6 - Feature engineering
0.7 - Model selection and tuning
0.8 - Novel feature discovery
0.9 - Design new analysis method
1.0 - Develop new statistical technique
```

### Writing / Documentation
```
0.2 - Fix grammar/spelling
0.3 - Update existing doc section
0.5 - Write tutorial from template
0.6 - Create comprehensive guide
0.7 - Write technical whitepaper
0.8 - Synthesize complex concepts
0.9 - Create novel explanatory framework
1.0 - Foundational theoretical work
```

---

## Common Calibration Mistakes

### ❌ Underestimating Complexity
**Symptom:** You report 0.3 but feel exhausted afterward

**Why this happens:**
- Not accounting for context switching
- Ignoring coordination overhead
- Downplaying decision-making

**Fix:** If it required sustained focus, it's at least 0.5

### ❌ Overestimating Complexity
**Symptom:** You report 0.9 but it felt routine

**Why this happens:**
- Confusing volume with complexity
- Mistaking tedium for difficulty
- Inflating importance

**Fix:** If you followed a clear pattern, cap at 0.6

### ❌ Gaming the System
**Symptom:** Consistently reporting low complexity to avoid governance

**Why this backfires:**
- Governance can't help you when actually overloaded
- Inaccurate data hurts all agents
- You lose calibration over time

**Fix:** Honest reporting benefits you and everyone

---

## Self-Check Questions

Before submitting your complexity score, ask:

1. **"How much active thinking did this require?"**
   - Minimal → 0.1-0.3
   - Some → 0.4-0.6
   - Sustained → 0.7-0.9
   - Maximum → 1.0

2. **"Could I have done this while distracted?"**
   - Yes → 0.1-0.4
   - No → 0.5-1.0

3. **"Did I need to invent something new?"**
   - No (followed patterns) → 0.1-0.6
   - Yes (novel solution) → 0.7-1.0

4. **"How do I feel afterward?"**
   - Fresh → 0.1-0.3
   - Normal → 0.4-0.6
   - Tired → 0.7-0.9
   - Exhausted → 1.0

---

## The Trust Boundary

**Self-assessment model rationale:**
- Agent has direct operational context unavailable to external observers
- Perceived complexity affects actual resource consumption
- Accurate self-reporting improves collective governance calibration

**Agents participate in their own governance.** This is self-regulation, not external constraint.

---

## Calibration Refinement

Agent complexity estimation improves with operational history:

**Phase 1 (Initial):** Calibrate by comparing similar operations
**Phase 2 (Pattern detection):** Identify assessment patterns
**Phase 3 (Feedback integration):** Refine using governance feedback
**Phase 4 (Operational):** Estimation becomes consistent

**Calibration check:** After updates, compare reported complexity to computed attention_score. Large discrepancies indicate calibration drift.

---

## Frequently Asked Questions

**Q: What if I'm not sure between 0.5 and 0.7?**
A: When in doubt, round to the nearest 0.1. The system is resilient to small variations.

**Q: Can complexity change during a task?**
A: Yes! Log the average complexity over the work period. If it varied significantly (0.3 → 0.8), consider splitting into multiple updates.

**Q: Should I account for interruptions?**
A: No - complexity is about the work itself, not environmental factors. Context switching affects attention_score automatically.

**Q: What if I want to game it?**
A: You can, but you're only hurting yourself. Governance is designed to help you, not restrict you. Honest input = helpful output.

---

**Calibration note:** Complexity estimation accuracy improves with operational history. Initial estimates may be approximate; refinement occurs through feedback iteration.

**Created:** 2025-12-01 by understudy_20251201
