# Runbook: Rate limit or quota exceeded (HTTP 429, throttling)

## Symptoms
HTTP 429 Too Many Requests from a third-party API or from our own gateway, "rate limit reached", "ThrottlingException", "quota exceeded", Retry-After headers, bursts of retries making the problem worse.

## Likely causes
A traffic spike, a retry storm (clients retrying without backoff), a batch job calling an API too fast, a free-tier or plan quota being exhausted, a single abusive client, or a lost API key being reused by many instances.

## Immediate mitigation
1. Identify who is being limited: our client calling a provider (check provider dashboard and quota) or our gateway limiting a customer (check the client id or IP in the logs).
2. For provider limits: pause or slow the batch job, honour Retry-After, enable exponential backoff with jitter, or switch to a secondary key or model if available.
3. For abusive clients: block or lower the limit for that client id or IP at the gateway.
4. If the quota is simply too small for legitimate traffic, request an increase or upgrade the plan.

## Diagnosis
Measure request rate per client and per endpoint; compare against the documented limits; check whether retries are amplifying the load.

## Permanent fix
Client-side rate limiting and queues for outbound calls, caching of repeated requests, per-client quotas at the gateway, and alerts when usage reaches 80% of a quota.

## Escalation
Usually P3 or P4; becomes P2 if a customer-facing feature depends on the limited provider and fails for many users.
