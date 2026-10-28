# Runbook: Upstream / gateway failure (502 Bad Gateway, 504 Gateway Timeout)

## Symptoms
nginx or the ingress returns 502 or 504; error log shows "connect() failed (111: Connection refused) while connecting to upstream", "upstream prematurely closed connection", "no live upstreams" or "upstream timed out (110)". Users see error pages.

## Likely causes
The backend process is down or crash-looping, the backend is listening on a different port than configured, backend workers are exhausted so new connections are refused, the backend takes longer than proxy_read_timeout (504), or a deploy removed all healthy upstreams.

## Immediate mitigation
1. Check whether the backend is running: `kubectl get pods -l app=<service>` or `systemctl status <service>`; restart it if it is down.
2. Check the upstream health in the proxy (nginx upstream status, ingress endpoints: `kubectl get endpoints <service>`), and confirm the port matches the service configuration.
3. For 504s, check backend latency and database health; raise proxy_read_timeout only as a temporary measure.
4. If a deployment just happened, roll back to the previous revision.

## Diagnosis
Correlate the time the 5xx rate rose with deploys, pod restarts and upstream latency. Confirm with `curl -v http://<backend>:<port>/health` from the proxy host.

## Permanent fix
Readiness probes so the proxy only routes to healthy backends, connection draining during deploys, autoscaling on worker saturation, and alerts on the 5xx rate.

## Escalation
502 across all upstreams on a customer-facing domain is a P1: page the service owner and the platform team.
