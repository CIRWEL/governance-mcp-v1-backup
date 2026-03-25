#!/usr/bin/env bash
# backup_governance.sh — Daily PostgreSQL backup for UNITARES governance DB
# Scheduled via ~/Library/LaunchAgents/com.unitares.governance-backup.plist
#
# Dumps the governance database from the postgres-age Docker container,
# compresses with gzip, and retains the last 14 daily backups.

set -euo pipefail

BACKUP_DIR="$HOME/backups/governance"
CONTAINER="postgres-age"
DATABASE="governance"
KEEP_DAYS=14
LOG="$BACKUP_DIR/backup.log"

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M)
BACKUP_FILE="$BACKUP_DIR/governance_${TIMESTAMP}.sql.gz"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"
}

# Check Docker container is running
if ! docker inspect "$CONTAINER" --format='{{.State.Running}}' 2>/dev/null | grep -q true; then
    log "ERROR: Container '$CONTAINER' is not running"
    exit 1
fi

# Run pg_dump
log "Starting backup to $BACKUP_FILE"
if docker exec "$CONTAINER" pg_dump -U postgres "$DATABASE" | gzip > "$BACKUP_FILE"; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log "Backup complete: $BACKUP_FILE ($SIZE)"
else
    log "ERROR: pg_dump failed"
    rm -f "$BACKUP_FILE"
    exit 1
fi

# Prune old backups (keep last N)
PRUNED=$(ls -1t "$BACKUP_DIR"/governance_*.sql.gz 2>/dev/null | tail -n +$((KEEP_DAYS + 1)) | wc -l | tr -d ' ')
ls -1t "$BACKUP_DIR"/governance_*.sql.gz 2>/dev/null | tail -n +$((KEEP_DAYS + 1)) | xargs rm -f 2>/dev/null || true
if [ "$PRUNED" -gt 0 ]; then
    log "Pruned $PRUNED old backup(s)"
fi

# Trim log (keep last 200 lines)
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 200 ]; then
    tail -200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
