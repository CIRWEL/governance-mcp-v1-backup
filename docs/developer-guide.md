# Developer Guide: Protecting Your Repo from Agent Damage

**This guide exists because agents have destroyed work in this repo.** February 2026: a Claude session force-pushed origin/master (rewriting all commit SHAs), left uncommitted bug fixes in the working tree, and caused hours of confusion by spawning the wrong PostgreSQL instance. This is the prevention guide.

## What agents can destroy

- **History rewriting** via `filter-repo`, `rebase -i`, `commit --amend` followed by `push --force`
- **Working tree destruction** via `reset --hard`, `checkout .`, `clean -f`
- **Branch deletion** via `branch -D`, `push --delete`
- **File deletion** via `rm -rf`, `git clean`
- **Service disruption** via unintended restarts, config changes, dependency modifications
- **Database destruction** via `DROP SCHEMA`, `TRUNCATE`, `DELETE FROM` without WHERE
- **Credential exposure** via committing `.env` files or printing secrets

---

## Tier 1: Essential (do these today)

### Back up before agent sessions

```bash
# Quick backup of working state (includes untracked files)
git stash push -u -m "pre-agent-session-$(date +%Y%m%d-%H%M%S)"

# Verify the stash captured everything
git stash show -u stash@{0}

# After the session, restore if needed
git stash pop
```

The `-u` flag is critical — without it, `git stash` only saves tracked files. Untracked files (new code, configs, test data) remain exposed to `clean -f` or `reset --hard`.

### Set up branch protection

On GitHub, protect `master`/`main`:
- Require pull request reviews
- Disable force pushes
- Require status checks to pass

This is the single most effective safeguard. It makes `git push --force origin master` fail server-side.

### Verify agent constraints

Before handing control to a Claude session, confirm your `.claude/settings.json` or `CLAUDE.md` includes:

```
Do NOT force push, reset --hard, clean -f, checkout ., or delete branches without explicit approval.
Do NOT run DROP, TRUNCATE, or DELETE without WHERE on any database.
Do NOT start, stop, or restart Docker containers without explicit approval.
Always use `docker exec postgres-age psql -U postgres -d governance` for database queries — never bare `psql`.
```

---

## Tier 2: Infrastructure awareness

### Database access (the right way)

There is ONE PostgreSQL and it's in Docker:

```bash
# Correct — always go through Docker
docker exec postgres-age psql -U postgres -d governance -c "\dt core.*"

# WRONG — hits Homebrew PostgreSQL (empty, different instance)
psql -d governance  # DO NOT USE
```

The Homebrew `postgresql@17` (port 5433) is an unrelated database. It has caused false "database is empty" panics. It should never be started for UNITARES work.

### Service management

```bash
# Check what's running
launchctl list | grep unitares
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

# Restart governance (if needed)
launchctl unload ~/Library/LaunchAgents/com.unitares.governance-mcp.plist
launchctl load ~/Library/LaunchAgents/com.unitares.governance-mcp.plist

# Health check
curl -s http://localhost:8767/health | python3 -m json.tool
```

### Git recovery

If an agent force-pushed or rebased:

```bash
# Your local reflog has the truth
git reflog

# Find the commit before the damage
git log --oneline <pre-damage-sha>

# Reset to it
git reset --hard <pre-damage-sha>

# Force push to fix remote (only if you're sure)
git push --force-with-lease origin master
```

If commits were lost on remote but exist locally, `git push` will fail with "fetch first" — this means the remote diverged. Use `git rebase origin/master` to replay your local work on top, then push.

---

## Tier 3: Monitoring

### Post-session audit

After any agent session, check:

```bash
# What changed?
git status
git diff
git log --oneline -5

# Are we ahead/behind remote?
git log origin/master..master --oneline  # local-only commits
git log master..origin/master --oneline  # remote-only commits

# Any force-push evidence?
git reflog | grep forced

# Database intact?
docker exec postgres-age psql -U postgres -d governance \
  -c "SELECT count(*) FROM core.dialectic_sessions; SELECT count(*) FROM core.agents;"
```

### Incident log

| Date | What happened | Root cause | Prevention |
|------|---------------|------------|------------|
| 2026-02-25 | origin/master force-pushed, all SHAs rewritten | Agent ran rebase + force push | Branch protection on GitHub |
| 2026-02-25 | "Database empty" false alarm | Homebrew PG intercepting connections | Always use `docker exec` |
| 2026-02-25 | 5 bug fixes left uncommitted in working tree | Agent didn't commit before ending session | Post-session audit |

---

**Updated:** 2026-02-26
