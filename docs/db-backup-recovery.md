# Database Backup & Recovery Runbook

## Overview

The ModishLog database runs in a Docker named volume (`modishlog_postgres_data`) inside a Colima VM. This document covers how to back up the database and how to recover it if the VM or Docker storage becomes corrupted.

---

## Routine Backup (pg_dump — preferred)

Run this whenever you want a portable SQL dump you can restore to any PostgreSQL instance.

```bash
# Dump to a timestamped file
docker exec modishlog-db-1 pg_dump -U modishlog modishlog \
  > ~/modishlog-pg-recovery/modishlog_$(date +%Y%m%d_%H%M%S).sql

# Verify the dump is non-empty
wc -l ~/modishlog-pg-recovery/modishlog_*.sql | tail -1
```

**Restore from a SQL dump:**

```bash
# Drop and recreate the database (data loss — confirm first)
docker exec modishlog-db-1 psql -U modishlog -c "DROP DATABASE IF EXISTS modishlog;"
docker exec modishlog-db-1 psql -U modishlog -c "CREATE DATABASE modishlog OWNER modishlog;"

# Restore
docker exec -i modishlog-db-1 psql -U modishlog -d modishlog \
  < ~/modishlog-pg-recovery/modishlog_<timestamp>.sql
```

---

## Emergency Recovery — Corrupted Colima VM Disk

Use this procedure when Docker has I/O errors, containers fail to exec, or `docker exec` returns `input/output error`.

**What happened (Jun 2026 incident):** Colima's ext4 filesystem developed corrupted orphaned inodes and block bitmap mismatches after an improper shutdown. Docker's overlay2 storage became unreadable but the named volume data survived intact on disk.

### Prerequisites

```bash
brew install e2fsprogs   # provides debugfs and e2fsck
```

### Step 1 — Extract a safe copy (VM can be running)

If Docker is completely broken but the VM is still running (containers show I/O errors), first stop Colima to unlock the disk:

```bash
colima stop
```

### Step 2 — Attach the VM disk read-only

```bash
# -readonly is enough to inspect; write access needed for e2fsck repair
hdiutil attach -nomount -imagekey diskimage-class=CRawDiskImage \
  ~/.colima/_lima/colima/diffdisk
```

Note the device path printed (e.g. `/dev/disk4`). The Linux root partition will be listed as **Linux Filesystem** — typically `/dev/disk4s1`.

### Step 3 — Repair the ext4 filesystem (if needed)

If `debugfs` refuses to open the partition with "Block bitmap checksum does not match", the filesystem needs repair. Reattach with write access (omit `-readonly`) and run:

```bash
/opt/homebrew/opt/e2fsprogs/sbin/e2fsck -y /dev/disk4s1
```

Wait for it to complete — it will fix orphaned inodes, block bitmap mismatches, and free-count errors. The summary line looks like:
```
cloudimg-rootfs: ***** FILE SYSTEM WAS MODIFIED *****
cloudimg-rootfs: 1319867/12976128 files ...
```

### Step 4 — Extract the PostgreSQL data directory

```bash
mkdir -p ~/modishlog-pg-recovery

/opt/homebrew/opt/e2fsprogs/sbin/debugfs \
  -R "rdump /var/lib/docker/volumes/modishlog_postgres_data/_data \
      /Users/sojisoyoye/modishlog-pg-recovery/" \
  /dev/disk4s1
```

"Operation not permitted while changing ownership" messages are expected (macOS can't set Linux UIDs) — the file content is copied correctly regardless.

Verify the extraction:

```bash
ls ~/modishlog-pg-recovery/_data/       # should show base/, pg_wal/, global/, etc.
du -sh ~/modishlog-pg-recovery/         # ~65 MB for this project
```

### Step 5 — Detach the disk and restart Colima

```bash
hdiutil detach /dev/disk4
colima start
```

### Step 6 — Verify the stack recovers automatically

After Colima starts, Docker usually recovers the named volume automatically from the repaired filesystem:

```bash
cd ~/workspace/modishlog
docker compose up -d

# Confirm all 52 tables are present
docker exec modishlog-db-1 psql -U modishlog -d modishlog -c "\dt" | wc -l
```

If the DB container fails to start, proceed to Step 7.

### Step 7 — Manual restore from extracted data (if Step 6 fails)

```bash
# Stop the broken DB container
docker compose stop db

# Remove the corrupted volume
docker volume rm modishlog_postgres_data

# Recreate an empty volume and seed it from the extracted data
docker volume create modishlog_postgres_data

# Start a temporary postgres container with both the empty volume
# and the extracted data directory bind-mounted
docker run --rm \
  -v modishlog_postgres_data:/target \
  -v ~/modishlog-pg-recovery/_data:/source:ro \
  alpine sh -c "cp -a /source/. /target/"

# Start the stack — postgres will find its data directory ready
docker compose up -d
```

---

## Backup Location

Current recovery backup: `~/modishlog-pg-recovery/_data/` (extracted Jun 12 2026, ~65 MB)

For longer-term storage, copy this to a safe location:

```bash
cp -r ~/modishlog-pg-recovery/_data ~/Desktop/modishlog-db-backup-$(date +%Y%m%d)
```

---

## Quick Reference

| Task | Command |
|---|---|
| SQL dump | `docker exec modishlog-db-1 pg_dump -U modishlog modishlog > ~/modishlog-pg-recovery/dump_$(date +%Y%m%d).sql` |
| Check DB healthy | `docker exec modishlog-db-1 psql -U modishlog -d modishlog -c "\dt" \| wc -l` |
| Stop Colima | `colima stop` |
| Start Colima | `colima start` |
| Repair ext4 | `/opt/homebrew/opt/e2fsprogs/sbin/e2fsck -y /dev/disk4s1` |
| Extract volume | `/opt/homebrew/opt/e2fsprogs/sbin/debugfs -R "rdump /var/lib/docker/volumes/modishlog_postgres_data/_data ~/modishlog-pg-recovery/" /dev/disk4s1` |
