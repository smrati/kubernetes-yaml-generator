---
kind: ConfigMap
summary: Non-secret configuration, stored in the cluster and read by Pods.
---

A ConfigMap holds key-value pairs of plain text, and Pods can read it either as
environment variables or as files mounted into a volume.

It exists so that configuration is not baked into the image. The same image can
run in staging and in production, and you change the behaviour by changing the
ConfigMap rather than by rebuilding and redeploying.

## Use it for

- Configuration that changes: feature flags, endpoints, log levels.
- Small files an application reads at startup.

## Use something else for

- Anything sensitive → [Secret](/form?apiVersion=v1&kind=Secret)
- Configuration that changes so often it should not be in the cluster at all →
  an environment variable set by the CI pipeline.

## Watch out for

**A ConfigMap is not a secret store.** Its values are plain text, readable by
anyone who can read the ConfigMap, and visible in `kubectl get configmap -o
yaml`. The name says configuration, not credentials.

The second thing is how a Pod consumes one. `envFrom` pulls every key in as an
environment variable, which means a key that is not a valid environment variable
name is silently skipped. `env` with an explicit `valueFrom.configMapKeyRef`
names the key and fails loudly if it is missing — which is usually what you want.

The third is that mounting a ConfigMap as a volume updates the files in place,
but the application has to notice. Kubernetes does not restart the Pod.
