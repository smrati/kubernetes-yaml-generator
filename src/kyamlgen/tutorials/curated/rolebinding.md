---
kind: RoleBinding
summary: Grants a Role's permissions to subjects, within one namespace.
---

A RoleBinding joins three things: a subject (who), a role reference (what), and
a namespace (where). It is the only object that actually grants access.

The subject is usually a [ServiceAccount](/form?apiVersion=v1&kind=ServiceAccount),
identified by name and namespace. It can also be a user or a group, but those
names only resolve if the cluster is configured with an external identity
provider.

## Use it for

- Giving a workload in namespace `app` read access to ConfigMaps in namespace
  `app`.

## Use something else for

- Cluster-wide grants →
  [ClusterRoleBinding](/form?apiVersion=rbac.authorization.k8s.io/v1&kind=ClusterRoleBinding).
- Cross-namespace grants of a namespaced Role → not possible. A RoleBinding can
  only reference a Role in its own namespace; to grant a namespaced Role across
  namespaces you bind a
  [ClusterRole](/form?apiVersion=rbac.authorization.k8s.io/v1&kind=ClusterRole)
  instead.

## Watch out for

**A binding whose role or subject does not exist is accepted and grants
nothing.** There is no error at creation time. If the Role is created later, the
binding starts working; if it never is, the subject silently has no access — and
"403 forbidden" is the only symptom.

**`roleRef` is immutable.** You cannot change which role a binding points at.
The fix is to delete the binding and create a new one. (Somewhat awkwardly, the
API server tolerates changing `apiGroup` and `kind` within the same request,
which is a wart rather than a feature.)

The third is that the subject's namespace is inside `subjects[].namespace`, not
the binding's. A binding in namespace `app` can grant to a ServiceAccount in
namespace `other` — but only a namespaced Role, which then also has to exist in
`app`.
