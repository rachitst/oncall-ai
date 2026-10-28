# Runbook: Out of memory (OOM)

## Symptoms
Kernel log "Out of memory: Killed process", container terminated with reason OOMKilled and exit code 137, `java.lang.OutOfMemoryError`, Python `MemoryError`, services restarting repeatedly with no application error logged.

## Likely causes
Memory leak, an unbounded cache or queue, a batch job loading a whole dataset into memory, container memory limit set too low for the workload, too many worker processes per container, or a sudden increase in request size.

## Immediate mitigation
1. Restart the affected process or let the orchestrator restart it; confirm traffic is served by healthy replicas.
2. Raise the container memory limit temporarily (for example 512Mi to 1Gi) if the node has capacity.
3. Reduce concurrency: fewer worker processes or threads per container, smaller batch sizes for jobs.
4. If the OOM started after a deploy, roll back.

## Diagnosis
Check memory over time with `kubectl top pod` or node metrics to distinguish a slow leak (steady climb) from a spike (single large request or job). Inspect heap dumps (`jmap`, `tracemalloc`) or the request that preceded the kill. Verify requests/limits in the pod spec.

## Permanent fix
Fix the leak or bound the cache, stream large data instead of loading it fully, set realistic memory requests and limits, add memory-based autoscaling and alerts at 80% of the limit.

## Escalation
Escalate to the service owner if restarts recur more than three times in an hour; treat as P1 if the OOM affects a customer-facing path in production.
