# Runbook: TLS certificate expired or invalid

## Symptoms
"certificate has expired", "CERTIFICATE_VERIFY_FAILED", "x509: certificate has expired or is not yet valid", "sslv3 alert certificate expired", curl error 60; clients and service-to-service calls fail at the TLS handshake, browsers show a security warning.

## Likely causes
The certificate reached its NotAfter date and automatic renewal (cert-manager, certbot, ACME) failed or was never configured, a renewed certificate was not deployed or the service was not reloaded, the chain or intermediate is wrong, or a client machine has the wrong clock.

## Immediate mitigation
1. Confirm the expiry: `openssl s_client -connect <host>:443 -servername <host> | openssl x509 -noout -dates`.
2. Renew and deploy: `certbot renew --force-renewal` or `kubectl describe certificate <name>` and `kubectl delete certificaterequest ...` to retrigger cert-manager; then reload nginx or restart the ingress pods.
3. If renewal is blocked (DNS or HTTP challenge failing), temporarily issue a certificate from the internal CA or a manually purchased one.
4. Check the system clock on the failing clients if only some clients fail.

## Diagnosis
Check the issuer logs (cert-manager events, certbot logs) for why renewal failed: DNS validation, rate limits, revoked tokens, wrong hostnames.

## Permanent fix
Automated renewal with monitoring, alerts at 30, 14 and 7 days before expiry, an inventory of all certificates and their owners, and renewal tests in staging.

## Escalation
An expired certificate on a public domain is P1 (all HTTPS traffic fails). Internal-only certificates in staging or dev are P3.
