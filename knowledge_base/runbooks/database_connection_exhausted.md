# Runbook: Database connection pool exhausted

## Symptoms
Errors such as "FATAL: too many connections", "remaining connection slots are reserved", "QueuePool limit of size N overflow M reached", "HikariPool-1 - Connection is not available", "could not obtain connection from pool". Requests that need the database time out while CPU on the database host is often low.

## Likely causes
Connection leak in application code (connections opened but never returned to the pool), a traffic spike with an undersized pool, a long-running transaction or lock holding connections, too many application replicas each with its own pool, or a database restart that invalidated pooled connections.

## Immediate mitigation
1. Check current connections on PostgreSQL: `SELECT count(*), state FROM pg_stat_activity GROUP BY state;` and `SHOW max_connections;`.
2. Terminate idle-in-transaction sessions older than 5 minutes: `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle in transaction' AND state_change < now() - interval '5 minutes';`.
3. If a recent deploy introduced the leak, roll back that service.
4. Temporarily scale down the number of application replicas, or raise `max_connections` only if the database host has memory headroom (each connection costs roughly 5-10 MB).

## Diagnosis
Compare `pg_stat_activity` by application_name to find the service holding most connections. Check the application pool settings (pool_size, max_overflow, maximumPoolSize) against replicas x pool_size versus max_connections. Look for queries stuck on locks with `pg_locks`.

## Permanent fix
Put a connection pooler (PgBouncer in transaction mode) in front of the database, set pool sizes so that replicas x pool_size stays below max_connections with a margin, add statement and idle-in-transaction timeouts, and fix leaking code paths (use context managers / try-finally to release connections).

## Escalation
Page the database owner if the primary is unresponsive or if terminating sessions does not restore service within 10 minutes.
