# Runbook: High latency and request timeouts

## Symptoms
p95 or p99 latency alerts, "upstream timed out", "context deadline exceeded", "ReadTimeout", slow query logs with durations in seconds, request queues growing, timeouts cascading between services.

## Likely causes
A slow database query (missing index, lock contention, table bloat), a saturated dependency, insufficient replicas for the traffic, garbage-collection pauses, a noisy neighbour on shared infrastructure, or a downstream API that became slow.

## Immediate mitigation
1. Locate the slow layer with traces or metrics: database, cache, external API or the service itself.
2. For slow queries, find them with `pg_stat_statements` or the slow query log; cancel runaway queries; add the missing index if obvious.
3. Scale out the service or the dependency if it is saturated; shed load or enable a circuit breaker for the slow downstream.
4. Reduce timeouts and retries so that one slow dependency does not consume all workers.

## Diagnosis
Compare latency percentiles before and after the incident started, correlate with deploys, traffic changes and database metrics (locks, connections, cache hit ratio).

## Permanent fix
Indexes and query optimisation, caching, timeouts and circuit breakers for every dependency, capacity planning with load tests, and SLOs with latency alerts.

## Escalation
Sustained p99 above the SLO for a customer-facing endpoint is P2; if requests fail outright for most users it is P1.
