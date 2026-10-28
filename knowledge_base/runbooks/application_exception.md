# Runbook: Unhandled application exception

## Symptoms
Stack traces in the application log: Python `Traceback (most recent call last)` ending in KeyError, AttributeError on NoneType, TypeError or IndexError; Java `NullPointerException`; requests returning HTTP 500 for specific inputs while other requests succeed.

## Likely causes
Unexpected or missing data (a field absent from an upstream response or database row), a schema or API contract change, a null value where the code assumed a value, a new code path shipped without tests, or bad input that is not validated.

## Immediate mitigation
1. Identify the request or record that triggers it from the trace (endpoint, request id, record id) and how many users are affected.
2. If it started after a deploy, roll back.
3. If it is data-specific, quarantine or fix the bad record so the path recovers.
4. Add a temporary guard (feature flag, try/except with a safe default) if a hotfix can be shipped quickly.

## Diagnosis
Reproduce locally with the failing input, check recent changes to the module in the trace, and compare the upstream response or database schema with what the code expects.

## Permanent fix
Input validation and schema checks at boundaries, explicit handling of optional values, unit tests for the failing case, and error tracking (Sentry-style) with alert thresholds.

## Escalation
Sporadic exceptions with no user impact are P3 or P4; an exception on a core path such as checkout or payment that fails for many users is P2 or P1.
