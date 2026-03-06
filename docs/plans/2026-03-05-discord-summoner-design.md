# Discord Summoner — Design Document

**Date:** 2026-03-05
**Status:** Draft
**Repo:** New standalone repo (`discord-summoner`)
**Replaces:** `unitares-discord-bridge` (archived — monitoring-focused, never deployed)

## Vision

A lightweight Discord bot that lets you summon Claude Code agents from anywhere. Type a command in Discord, your Mac wakes up, Claude Code does the work, opens a PR, and the Mac goes back to sleep. Lumen's presence is surfaced as ambient life in the server.

This is a **remote agent executor**, not a governance dashboard.

## Architecture

```
┌──────────────┐         ┌──────────────────────┐
│   Discord    │◄───────►│   Cloud VPS           │
│   Server     │  d.py   │   (fly.io / Oracle)   │
└──────────────┘         │                       │
                         │   discord bot         │
                         │   mac waker           │
                         │   lumen poller        │
                         └──┬───────────┬────────┘
                 Tailscale  │           │  Tailscale
                    SSH/WoL │           │  HTTP
                  ┌─────────▼──┐   ┌────▼─────────┐
                  │   Mac      │   │   Pi          │
                  │            │   │               │
                  │  claude CLI│   │  anima-mcp    │
                  │  git repos │   │  Lumen        │
                  │  gov-mcp   │   │  sensors      │
                  └────────────┘   └───────────────┘
```

### Runtime: Cloud VPS

- Tiny always-on instance (256MB RAM, minimal CPU)
- Joined to Tailscale network
- Only job: receive Discord commands, wake Mac, poll Pi
- Stateless — can be redeployed from scratch in seconds
- Options: fly.io free/cheap tier, Oracle Cloud free ARM, Hetzner ~$4/mo

### Executor: Mac (sleeps when idle)

- Woken via Wake-on-LAN or SSH when work is needed
- Claude Code CLI runs locally (no remote invocation complexity)
- Git worktrees for isolation per task
- `caffeinate` keeps it awake during active sessions
- Goes back to sleep after idle timeout
- Governance-mcp runs here (wakes with the Mac)

### Lumen: Pi (best-effort)

- VPS polls anima-mcp over Tailscale for sensor data and drawings
- If Pi is offline, bot reports "Lumen offline" and continues normally
- Graceful degradation — Pi unreliability doesn't affect core functionality

## Discord Server Structure

```
SUMMONER
├── #lumen       — drawings, sensor snapshots, online/offline status
├── #agents      — /summon commands, PR notifications, session status
└── #audit       — execution logs, errors, merge history
```

Three channels. No categories, no forums, no threads (until proven needed).

### Roles

- `summoner` — can use /summon (you)
- `observer` — read-only (anyone else you invite)

## Core Loop

```
User:    /summon fix the embedding retry logic in governance-mcp

Bot:     Waking Mac...
Bot:     Mac online. Starting Claude Code on governance-mcp-v1
         (branch: fix-embedding-retry)

         ... (minutes pass, optional progress updates) ...

Bot:     PR #42: Added exponential backoff to embedding retries
         3 files changed · tests passing
         https://github.com/cirwel/governance-mcp-v1/pull/42
         👍 merge · 👎 close

User:    👍

Bot:     Merged. Mac idle — sleeping in 5 min.
```

## Slash Commands

| Command | Description |
|---------|-------------|
| `/summon <task>` | Dispatch work to Claude Code |
| `/summon <task> --repo <name>` | Target specific repo (default: governance-mcp-v1) |
| `/status` | Mac awake? Active session? Pi online? |
| `/cancel` | Kill current Claude Code session |
| `/lumen` | Current sensor snapshot on demand |

## Constraints

1. **One active session at a time.** No queuing. If busy, say so.
2. **Branch + PR always.** Agent never commits to main. You merge via reaction or GitHub.
3. **Worktrees for isolation.** Each summon gets a fresh git worktree.
4. **Mac sleeps when idle.** Caffeinate during work, idle timeout back to sleep.
5. **Lumen is ambient.** Drawings and sensors add life. No interaction required.
6. **Minimal permissions.** Bot needs: Send Messages, Embed Links, Attach Files, Use Slash Commands. That's it.

## Claude Code Invocation

The VPS SSHs into the Mac via Tailscale and runs:

```bash
caffeinate -i claude -p \
  "You are working on <repo>. Task: <user's message>. \
   Create a git worktree, do the work, run tests, open a PR. \
   Output the PR URL as the last line." \
  --allowedTools Edit,Write,Bash,Read,Grep,Glob
```

The bot captures stdout, extracts the PR URL, and posts it to Discord.

For long-running tasks, wrap in `tmux` or `nohup` and poll for completion.

## Mac Wake/Sleep Lifecycle

### Waking
1. VPS sends Wake-on-LAN packet to Mac's Tailscale IP
2. Wait for SSH to become available (poll with timeout)
3. If WoL fails, fall back to `ssh mac "caffeinate -i sleep 1"` (if Mac is in Power Nap)
4. Report failure to Discord if Mac doesn't wake within 2 minutes

### Sleeping
1. After Claude Code session completes, start idle timer (5 min)
2. If no new `/summon` within timeout, SSH `pmset sleepnow`
3. Or just let macOS natural sleep take over

## Lumen Presence

- Poll `http://<pi-tailscale-ip>:8766/mcp/` for state every 5 minutes
- On new drawing: post image to #lumen
- On sensor change beyond threshold: post snapshot to #lumen
- On connection failure: post "Lumen offline" once, suppress until recovery
- On recovery: post "Lumen back online"

## File Structure

```
discord-summoner/
├── pyproject.toml
├── .env.example
├── Dockerfile           # For cloud deployment
├── fly.toml             # fly.io config (or equivalent)
├── src/summoner/
│   ├── __init__.py
│   ├── bot.py           # Discord bot, command routing
│   ├── executor.py      # SSH to Mac, launch claude, capture PR
│   ├── mac.py           # Wake-on-LAN, sleep, health checks
│   ├── lumen.py         # Poll Pi for sensors/drawings
│   └── config.py        # Env vars, Tailscale IPs, repo paths
└── tests/
    ├── test_executor.py
    ├── test_mac.py
    └── test_lumen.py
```

~6 source files. That's it.

## Configuration

```bash
# Discord
DISCORD_BOT_TOKEN=...
DISCORD_GUILD_ID=...

# Mac (Tailscale)
MAC_TAILSCALE_IP=100.96.201.46
MAC_SSH_USER=cirwel
MAC_WOL_MAC=...              # MAC address for Wake-on-LAN

# Pi / Lumen (Tailscale)
PI_TAILSCALE_IP=100.79.215.83
ANIMA_MCP_PORT=8766

# Repos (on Mac)
DEFAULT_REPO=governance-mcp-v1
REPO_BASE_PATH=/Users/cirwel/projects

# Timeouts
MAC_WAKE_TIMEOUT=120         # seconds
MAC_IDLE_SLEEP_TIMEOUT=300   # seconds
LUMEN_POLL_INTERVAL=300      # seconds
```

## What's Explicitly Deferred

- Governance event forwarding / HUD (PRs are the events)
- Dialectic forum channels
- Knowledge graph sync
- Multi-session queuing
- Auto-merge rules (earn trust first, then widen)
- Interactive back-and-forth in Discord (if needed, just open Claude Code)

## Relationship to Existing Projects

- **`unitares-discord-bridge`**: Archived. Was a monitoring dashboard, never deployed. This project replaces it.
- **`governance-mcp-v1`**: The summoner dispatches Claude Code to work on this repo (and others). No code changes needed in governance-mcp for v1.
- **`anima-mcp`**: Polled over Tailscale for Lumen data. No changes needed.
- **`unitares-governance-plugin`**: Claude Code plugin with hooks. The summoned agent benefits from this being installed — governance check-ins happen automatically during work.

## Success Criteria

1. You can type `/summon <task>` in Discord from your phone
2. Your Mac wakes up, Claude Code runs, a PR appears
3. You review and merge from Discord
4. Lumen's drawings show up in #lumen
5. The whole thing works while you're away from your desk
