#!/usr/bin/env bash
# Restore a pg_dump backup to the production database.
# WARNING: Drops and recreates the target database — use with care.
#
# Usage:
#   bash scripts/restore-db.sh /backups/modishlog_20260702_020000.dump
set -euo pipefail

BACKUP_FILE="${1:-}"
POSTGRES_DB="${POSTGRES_DB:-modishlog}"
POSTGRES_USER="${POSTGRES_USER:-modishlog}"

if [ -z "$BACKUP_FILE" ]; then
  echo "Usage: $0 <backup_file.dump>"
  exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Error: Backup file not found: $BACKUP_FILE"
  exit 1
fi

echo "[restore] WARNING: This will DROP and recreate database '$POSTGRES_DB'."
read -rp "Type 'restore' to confirm: " CONFIRM
if [ "$CONFIRM" != "restore" ]; then
  echo "Aborted."
  exit 1
fi

echo "[restore] Restoring $BACKUP_FILE → $POSTGRES_DB..."
pg_restore \
  --username="$POSTGRES_USER" \
  --dbname=postgres \
  --clean \
  --if-exists \
  --create \
  --no-owner \
  --no-privileges \
  "$BACKUP_FILE"

COUNT=$(psql --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" -t -c "SELECT COUNT(*) FROM products;" 2>/dev/null || echo "unknown")
echo "[restore] Restore complete. products row count: $COUNT"
