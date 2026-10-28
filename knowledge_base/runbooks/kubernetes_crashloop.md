# Runbook: Kubernetes CrashLoopBackOff

## Symptoms
Pod status CrashLoopBackOff, "Back-off restarting failed container", increasing restart count, liveness or readiness probes failing, the application exits shortly after start.

## Likely causes
The application crashes on startup (missing environment variable, bad configuration, failed migration, missing secret or config map), the liveness probe is too aggressive or points at the wrong port or path, the container runs out of memory (OOMKilled), or a dependency (database, cache) is unreachable at startup.

## Immediate mitigation
1. Read the logs of the previous container: `kubectl logs <pod> --previous` and `kubectl describe pod <pod>` (look at Last State, Exit Code, Events).
2. Exit code 137 means OOMKilled (see the OOM runbook); exit code 1 or 2 usually means an application or configuration error; probe failures appear in Events.
3. If a deploy caused it, roll back: `kubectl rollout undo deployment/<name>`.
4. If the probe is wrong, relax `initialDelaySeconds` or fix the probe path while the real fix is prepared.

## Diagnosis
Reproduce by running the image locally with the same environment, confirm secrets and config maps exist in the namespace, and check whether dependencies were reachable at the crash time.

## Permanent fix
Validate configuration at startup with clear error messages, startup probes for slow-starting apps, sensible probe timings, and CI tests that run the container before deploying.

## Escalation
If all replicas of a production service are crash-looping, treat as P1 and page the service owner; a single replica or a non-production namespace is P3.
