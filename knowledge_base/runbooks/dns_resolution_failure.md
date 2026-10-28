# Runbook: DNS resolution failure

## Symptoms
"Temporary failure in name resolution", "getaddrinfo ENOTFOUND", "Could not resolve host", NXDOMAIN, CoreDNS i/o timeouts, "server misbehaving". Services cannot reach dependencies by name while IP connectivity works.

## Likely causes
CoreDNS or the resolver pods are overloaded or down, a DNS record was deleted or changed, a wrong search domain or resolv.conf after a node change, upstream DNS provider outage, or a TTL/caching problem after a migration.

## Immediate mitigation
1. Test from inside the environment: `nslookup <name>` and `dig <name> @10.0.0.10`; compare with a public resolver.
2. Check CoreDNS: `kubectl -n kube-system get pods -l k8s-app=kube-dns` and its logs; restart it if unhealthy, and scale it up if it is overloaded.
3. If a record was changed, restore it at the DNS provider; the fix propagates within the TTL.
4. As a short-term workaround, use the IP or a hosts-file entry for the critical dependency.

## Diagnosis
Determine whether the failure is for one name (record problem) or all names (resolver problem), and whether it is internal or external DNS.

## Permanent fix
Monitor DNS success rate and latency, keep CoreDNS replicas and resources sized for the cluster, protect critical records with change review, and use short but not tiny TTLs.

## Escalation
Resolver failure affecting all services in production is P1; a single internal name in staging is P3.
