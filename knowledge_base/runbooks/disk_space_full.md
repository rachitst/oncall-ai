# Runbook: Disk space exhausted

## Symptoms
"No space left on device" (ENOSPC), writes failing, PostgreSQL PANIC on pg_wal, Kubernetes node condition DiskPressure=True with pod evictions, inodes_free=0, services unable to write logs or temporary files.

## Likely causes
Log files growing without rotation, old Docker images and containers, large temporary or upload files, database WAL or backups accumulating, core dumps, or inode exhaustion from millions of small files.

## Immediate mitigation
1. Find the usage: `df -h` and `df -i`, then `du -xh --max-depth=2 /var | sort -h | tail`.
2. Free space safely: `journalctl --vacuum-size=200M`, `docker system prune -f`, delete rotated logs older than 7 days, remove known temporary directories.
3. Never delete database data files or WAL manually; for PostgreSQL, free space elsewhere and restart the database so it can recover.
4. If a Kubernetes node is under DiskPressure, cordon it and let pods reschedule while cleaning.

## Diagnosis
Identify which directory grew and since when, and whether a recent change (debug logging, a new job, a failing upload cleanup) caused it.

## Permanent fix
Configure logrotate and container log limits, schedule image pruning, move uploads and backups to object storage, add disk usage alerts at 80% and 90%, and set retention for WAL and backups.

## Escalation
Page the database owner immediately if the database volume is full; treat as P1 in production because writes are failing for all users.
