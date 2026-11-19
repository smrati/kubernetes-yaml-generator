---
kind: ServiceAccount
summary: The identity a Pod runs as — what it is allowed to do.
---

A ServiceAccount is an identity inside a namespace. When a Pod runs, it runs *as*
a ServiceAccount, and everything it does through the API server is authorised
against that identity.

Every namespace has a `default` ServiceAccount, and Pods use it unless told
otherwise. You create your own when you want permissions that are not
`default`'s, or when you want to bind a specific set of permissions to a
specific workload.

## Use it for

- Giving a workload its own identity, with its own
  [Role](/form?apiVersion=rbac.authorization.k8s.io/v1&kind=Role) bound to it.
- Automating a service account token mount for an in-cluster client.

## Use something else for

- A human user → an external identity provider. Kubernetes RBAC does not
  authenticate people.
- Permissions themselves → [Role](/form?apiVersion=rbac.authorization.k8s.io/v1&kind=Role)
  or [ClusterRole](/form?apiVersion=rbac.authorization.k8s.io/v1&kind=ClusterRole).

## Watch out for

**`automountServiceAccountToken` defaults to `true`.** Every Pod gets a token
for the `default` ServiceAccount mounted at
`/var/run/secrets/kubernetes.io/serviceaccount`, whether it needs one or not.
If your workload never talks to the API server, turn it off — that is free
security, and it is a per-Pod or per-ServiceAccount setting.

The second is that a ServiceAccount is just an identity. Creating one grants
nothing. The permissions come from a
[RoleBinding](/form?apiVersion=rbac.authorization.k8s.io/v1&kind=RoleBinding)
that names it.

The third is that ServiceAccounts are namespaced, and a
[RoleBinding](/form?apiVersion=rbac.authorization.k8s.io/v1&kind=RoleBinding) can
only bind a subject in its own namespace.
