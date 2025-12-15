# Tool Cognitive Load Reduction

**Problem:** 53 tools create decision paralysis for agents. Started with ~6 tools, now overwhelming.

**Analysis:**
- **9 Essential tools** (50+ calls): Core workflow tools
- **25 Common tools** (10-49 calls): Moderately used
- **16 Rare tools** (<10 calls): Candidates for hiding/consolidation

**Solution:** Tiered tool visibility with progressive disclosure.

## Tool Tiers

### Tier 1: Essential (Always Visible)
Core workflow tools that agents use daily:
- `process_agent_update` - Log work
- `store_knowledge_graph` - Save discoveries
- `search_knowledge_graph` - Find knowledge
- `get_agent_api_key` - Authentication
- `list_agents` - See other agents
- `get_governance_metrics` - Check status
- `get_discovery_details` - View details
- `get_dialectic_session` - Dialectic workflow
- `bind_identity` - Session management (new, should be promoted)

**Count:** ~9 tools

### Tier 2: Common (Visible by Default)
Tools used regularly but not daily:
- Knowledge graph operations (list, update status, find similar)
- Agent lifecycle (metadata, archive, delete)
- Observability (observe, compare, detect anomalies)
- Dialectic workflow (request review, submit thesis/antithesis/synthesis)
- Admin (health check, server info, telemetry)
- Export (system history, export to file)

**Count:** ~25 tools

### Tier 3: Advanced (Hidden by Default)
Rarely-used tools, shown on demand:
- `simulate_update` - Testing only
- `set_thresholds` - Admin override
- `reset_monitor` - Emergency reset
- `cleanup_stale_locks` - Maintenance
- `archive_old_test_agents` - Bulk operations
- `direct_resume_if_safe` - Emergency recovery
- `backfill_calibration_from_dialectic` - Data migration
- `compare_me_to_similar` - Advanced comparison
- `validate_file_path` - Policy check (should be auto-called, not manual)
- `export_to_file` - Advanced export
- `update_agent_metadata` - Rare updates
- `find_similar_discoveries_graph` - Advanced search
- `reply_to_question` - Knowledge graph Q&A
- `leave_note` - Quick notes
- `request_exploration_session` - Advanced dialectic
- `get_workspace_health` - System diagnostics

**Count:** ~16 tools

## Implementation Strategy

### Option 1: Metadata-Based Filtering (Recommended)
Add `tier` metadata to tool definitions. `list_tools` returns:
- All tools by default (backward compatible)
- `essential_only=true` parameter to filter to Tier 1
- `include_advanced=false` to hide Tier 3

### Option 2: Progressive Disclosure
- Onboarding: Show only Tier 1 tools
- After first `process_agent_update`: Show Tier 2
- Advanced tools: Only shown when explicitly requested

### Option 3: Tool Groups
Group tools by category, show essential groups first:
- "Core Workflow" (Tier 1)
- "Knowledge Management" (Tier 2)
- "Advanced Operations" (Tier 3)

## Benefits

1. **Reduced cognitive load**: Agents see ~9 essential tools initially
2. **Progressive learning**: Discover tools as needed
3. **Backward compatible**: All tools still available
4. **Self-documenting**: Tool tiers reflect actual usage

## Migration Plan

1. Add `tier` field to tool metadata
2. Update `list_tools` to support filtering
3. Update onboarding docs to emphasize Tier 1
4. Monitor usage to adjust tiers over time

