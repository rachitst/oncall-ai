# Runbook: Deployment or rollout failure

## Symptoms
ImagePullBackOff or ErrImagePull ("manifest unknown", "not found"), "Deployment exceeded its progress deadline", "UPGRADE FAILED: timed out waiting for the condition", failed database migrations, automatic rollback messages, new pods never becoming Ready.

## Likely causes
The image tag was never pushed or has a typo, registry credentials expired, the new version crashes or fails readiness, a migration is incompatible with the running version, insufficient cluster resources for the new pods, or a bad Helm value.

## Immediate mitigation
1. Check the rollout: `kubectl rollout status deployment/<name>` and `kubectl describe pod <new-pod>` for the exact event.
2. If the old version is still serving traffic, pause and roll back: `kubectl rollout undo deployment/<name>` or `helm rollback <release> <revision>`.
3. For image problems, verify the tag exists in the registry and that the imagePullSecret is valid.
4. For failed migrations, restore from the pre-migration backup or run the down migration before retrying.

## Diagnosis
Compare the failing revision with the last good one (image, config, resources), and run the container locally with production-like configuration.

## Permanent fix
CI that builds and pushes images before deploying, pre-deploy checks (image exists, migration dry run), readiness probes, canary or blue-green rollouts, and automatic rollback on failed health checks.

## Escalation
A failed deploy that rolled back cleanly is P3; one that left production serving errors is P1 or P2 depending on user impact.
