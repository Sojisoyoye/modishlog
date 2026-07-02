#!/usr/bin/env bash
# Nightly PostgreSQL backup — runs inside the db container via cron or Docker entrypoint.
# Output: compressed pg_dump in BACKUP_DIR, then synced to remote via rclone.
#
# Environment (set in .env.production):
#   POSTGRES_DB     - database name (default: modishlog)
#   POSTGRES_USER   - database user (default: modishlog)
#   BACKUP_DIR      - local backup directory (default: /backups)
#   RCLONE_REMOTE   - rclone remote:path (e.g. "s3:modishlog-backups"), optional
#
# Usage (on VPS):
#   docker compose -f docker-compose.prod.yml exec db bash /scripts/backup-db.sh
set -euo pipefail

POSTGRES_DB="${POSTGRES_DB:-modishlog}"
POSTGRES_USER="${POSTGRES_USER:-modishlog}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
RCLONE_REMOTE="${RCLONE_REMOTE:-}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="modishlog_${TIMESTAMP}.dump"
FILEPATH="$BACKUP_DIR/$FILENAME"

mkdir -p "$BACKUP_DIR"

echo "[backup] Starting pg_dump for $POSTGRES_DB at $TIMESTAMP..."
pg_dump \
  --username="$POSTGRES_USER" \
  --format=custom \
  --compress=9 \
  --no-password \
  "$POSTGRES_DB" \
  > "$FILEPATH"

SIZE=$(du -sh "$FILEPATH" | cut -f1)
echo "[backup] Dump complete: $FILEPATH ($SIZE)"

# Upload to remote (S3, B2, etc.) via rclone if configured
if [ -n "$RCLONE_REMOTE" ] && command -v rclone &>/dev/null; then
  echo "[backup] Uploading to $RCLONE_REMOTE..."
  rclone copy "$FILEPATH" "$RCLONE_REMOTE/" --progress
  echo "[backup] Upload complete."
fi

# Retention: keep 7 daily + 4 weekly backups
# Delete files older than 28 days (keeping ~4 weekly)
echo "[backup] Pruning backups older than 28 days..."
find "$BACKUP_DIR" -name "modishlog_*.dump" -mtime +28 -delete
echo "[backup] Backup finished successfully."
