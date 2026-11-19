---
kind: Secret
summary: Sensitive values — passwords, tokens, certificates — stored in the cluster.
---

A Secret holds key-value pairs that you do not want in a ConfigMap: passwords,
API tokens, TLS keys.

What "sensitive" means here is worth being precise about, because the name
over-promises. A Secret's values are **base64-encoded, not encrypted**. Anyone
who can read the Secret can read the secret, and `kubectl get secret -o yaml`
prints the encoded values in plain sight. Base64 is an encoding, not a
protection.

The protection comes from access control — RBAC — and from the fact that
Secrets are not printed by default in `kubectl describe`.

## Use it for

- Passwords, API keys, tokens.
- TLS certificates and keys, usually as `kubernetes.io/tls`.

## Use something else for

- Non-sensitive configuration → [ConfigMap](/form?apiVersion=v1&kind=ConfigMap)
- Anything that should not be in the cluster at all → an external secret manager
  (Vault, AWS Secrets Manager) synced in by an operator.

## Watch out for

**Use `stringData`, not `data`.** `data` wants base64, which means you have to
encode every value by hand and there is no way to tell a typo from a secret.
`stringData` is plain text and the API server encodes it for you. The two are
merged on write, and `stringData` wins — so you can use both in one object.

The second is that a Secret mounted as a volume updates in place, and the
application has to notice. For environment variables it is worse: the values
are fixed when the Pod starts, so changing a Secret does nothing to a running
Pod until you restart it.

The third is that Secrets are namespaced. A Secret in `prod` is not readable
from `staging`, and there is no cluster-wide read.
