# Runbook: Authentication failure or credential issue

## Symptoms
HTTP 401 with "invalid token", "signature verification failed" or "token expired"; 403 Forbidden for a service account; many "Failed password" lines in sshd logs from one IP; users unable to log in.

## Likely causes
A rotated signing key or secret not propagated to all services, an expired token or certificate used for service-to-service auth, clock skew making tokens appear expired, a changed IAM policy or role, or a brute-force attack against SSH or the login endpoint.

## Immediate mitigation
1. Determine the scope: all users (likely a key or config change) versus one client (likely an expired or wrong credential).
2. For key rotation problems, redeploy the services with the new key or restore the previous key temporarily.
3. For clock skew, check NTP on the affected hosts.
4. For brute force, block the source IP with fail2ban or a firewall rule and confirm no login succeeded.
5. For 403 on a service account, compare the IAM policy with the last known good version and restore the permission.

## Diagnosis
Decode the failing token (header kid, exp, iss) and compare with the keys the service trusts; check audit logs for IAM changes; count failures per IP and per user.

## Permanent fix
Automated, versioned key rotation with overlap periods, short-lived tokens with refresh, NTP everywhere, rate limiting and lockout on login endpoints, and alerts on authentication failure spikes.

## Escalation
Login failing for all users in production is P1. A single service account or a brute-force attempt that is blocked is P3; an attack that succeeded is a security incident and must be escalated to the security team immediately.
