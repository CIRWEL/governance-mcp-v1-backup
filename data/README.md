# Data Directory

This directory contains runtime data, agent states, history, and knowledge for the UNITARES Governance system.

**⚠️ Important:** Many files in this directory contain sensitive information (API keys, agent data) and are **NOT** tracked in git.

---

## Organization

See [ORGANIZATION_GUIDE.md](../docs/ORGANIZATION_GUIDE.md) for complete organization standards.

### Quick Structure

Current organization uses an **organized structure** with subdirectories:

- `agents/` - Agent state files (`{agent_id}_state.json`)
- `history/` - Historical exports (`{agent_id}_history_{timestamp}.json`)
- `knowledge/` - Knowledge layer data
- `dialectic_sessions/` - Dialectic recovery sessions
- `archive/` - Archived data (agents/, history/, exports/)
- `test_files/` - Test data (safe for git)
- `processes/`, `locks/` - Runtime state (not in git)

---

## Files NOT in Git

- `agent_metadata.json` - Contains API keys
- `knowledge/` - May contain sensitive discoveries
- `audit_log.jsonl` - May contain sensitive information
- `archive/` - Historical sensitive data
- `locks/` - Runtime locks
- `processes/` - Process tracking

---

## Files Safe for Git

- `agent_metadata.example.json` - Example template
- `test_files/` - Test data (no real API keys)
- `README.md` files - Documentation

---

## Quick Reference

**Where do I put...?**

- **Active agent state:** `agents/{agent_id}_state.json`
- **History export:** `history/{agent_id}_history_{timestamp}.json`
- **Knowledge data:** `knowledge/{agent_id}_knowledge.json`
- **Test data:** `test_files/test_*.json`
- **Archived data:** `archive/agents/` or `archive/history/`

**See:** [ORGANIZATION_GUIDE.md](../docs/ORGANIZATION_GUIDE.md) for complete guidelines.

