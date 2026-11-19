---
kind: ClusterRoleBinding
summary: Grants a ClusterRole's permissions across the whole cluster.
---

A ClusterRoleBinding joins a subject to a ClusterRole, with no namespace
limitation on either side. It is the only object that grants cluster-wide
access.

It is also the object that most often grants *too much*, because the two ways of
using a ClusterRole look identical in a manifest and mean very different things.

## Use it for

- Cluster-level permissions, such as an operator that watches every namespace.
- Granting a ClusterRole to a group of users from an identity provider.

## Use something else for

- Cluster-wide permissions scoped to one namespace → bind the ClusterRole with a
  namespaced [RoleBinding](/form?apiVersion=rbac.authorization.k8s.io/v1&kind=RoleBinding)
  instead. Same role, one namespace.
- Namespace-scoped permissions → [Role](/form?apiVersion=rbac.authorization.k8s.io/v1&kind=Role)
  plus [RoleBinding](/form?apiVersion=rbac.authorization.k8s.io/v1&kind=RoleBinding).

## Watch out for

**A ClusterRoleBinding and a namespaced RoleBinding of the same ClusterRole
grant different amounts of access.** The cluster-wide one lets the subject read
every Secret in every namespace. The namespaced one lets it read Secrets in one
namespace. The manifests look almost identical, and the difference is the whole
security boundary.

The second is `roleRef`, which is immutable here too. Delete and recreate.

The third is that a ClusterRoleBinding can name a subject in any namespace, and
`subjects[].namespace` is where you put it. Omitting it means the
`default` namespace, which is almost never what was meant.
