# Script Relocation - December 1, 2025

## Summary

Moved user-facing scripts from project to `~/scripts/` for better organization.

---

## Rationale

**Problem:** User-facing utilities were mixed with project infrastructure in `~/projects/governance-mcp-v1/scripts/`

**Solution:** Separate user tools from project infrastructure

---

## What Was Moved

### User-Facing Scripts (→ ~/scripts/)

1. **`claude_code_bridge.py`** - Official CLI interface for governance
   - Updated to find project via `GOVERNANCE_MCP_DIR` env var
   - Falls back to `~/projects/governance-mcp-v1`
   - **Usage:** `python3 ~/scripts/claude_code_bridge.py --help`

2. **`setup_mcp.sh`** - MCP setup automation
   - **Usage:** `bash ~/scripts/setup_mcp.sh`

3. **`monitor_mcp_health.sh`** - Health monitoring
   - **Usage:** `bash ~/scripts/monitor_mcp_health.sh`

4. **`secure_mcp_config.sh`** - Security configuration
   - **Usage:** `bash ~/scripts/secure_mcp_config.sh`

### Stayed in Project

Project infrastructure scripts remain in `~/projects/governance-mcp-v1/scripts/`:

- `cleanup_zombie_mcp_servers.sh` - Process cleanup
- `check_eisv_completeness.py` - Pre-commit hook
- `archive_old_markdowns.py` - Maintenance
- `audit_markdown_proliferation.py` - Maintenance
- `auto_archive_metadata.py` - Maintenance
- `doc_tools.py` - Maintenance
- `validate_all.py` - Testing

---

## Changes Made

### 1. Script Relocation
- Moved 4 user-facing scripts to `~/scripts/`
- Updated `claude_code_bridge.py` path logic
- Added `GOVERNANCE_MCP_DIR` environment variable support

### 2. Documentation Updates
- Updated `docs/guides/ONBOARDING.md`
- Updated `docs/guides/TROUBLESHOOTING.md`
- Updated `docs/guides/MCP_SETUP.md`
- All examples now use `~/scripts/` paths

### 3. Path Logic
```python
# claude_code_bridge.py now uses:
PROJECT_DIR = Path(os.environ.get('GOVERNANCE_MCP_DIR',
                                   Path.home() / 'projects' / 'governance-mcp-v1'))
```

---

## New Directory Structure

```
~/scripts/                          # User utilities
├── claude_code_bridge.py           ✅ User runs this
├── setup_mcp.sh                    ✅ User runs this
├── monitor_mcp_health.sh           ✅ User runs this
├── secure_mcp_config.sh            ✅ User runs this
└── Archive/                        (historical scripts)

~/projects/governance-mcp-v1/
├── scripts/                        # Project infrastructure
│   ├── cleanup_zombie_mcp_servers.sh
│   ├── check_eisv_completeness.py
│   └── [maintenance scripts]
└── src/                            # Source code
```

---

## Usage

### Setting Custom Project Location

If your project is not at `~/projects/governance-mcp-v1`:

```bash
export GOVERNANCE_MCP_DIR=/path/to/your/governance-mcp-v1
python3 ~/scripts/claude_code_bridge.py --help
```

### Standard Usage

```bash
# CLI interface (most common)
python3 ~/scripts/claude_code_bridge.py --agent-id my_agent --log "Work done"

# Setup (run once)
bash ~/scripts/setup_mcp.sh

# Health check
bash ~/scripts/monitor_mcp_health.sh

# Security config
bash ~/scripts/secure_mcp_config.sh
```

---

## Benefits

1. **Clear Separation**
   - User tools in `~/scripts/`
   - Project infrastructure in project
   - No confusion about what to run

2. **Better Organization**
   - User scripts are globally accessible
   - Project scripts stay with project
   - Follows Unix conventions

3. **Flexibility**
   - Can move project anywhere
   - Set `GOVERNANCE_MCP_DIR` to new location
   - Scripts still work

---

**Status:** ✅ Complete
**Verified:** All scripts tested from new locations
**Docs Updated:** All references point to new paths
