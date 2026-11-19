---
kind: ClusterRole
summary: A set of permissions that can apply across the whole cluster.
---

A ClusterRole is a Role that is not bound to a namespace. It can be bound with a
[ClusterRoleBinding](/form?apiVersion=rbac.authorization.k8s.io/v1&kind=ClusterRoleBinding)
for cluster-wide access, or with a namespaced
[RoleBinding](/form?apiVersion=rbac.authorization.k8s.io/v1&kind=RoleBinding)
to grant those permissions inside one namespace only.

That second use is the one people miss. The same ClusterRole can grant "read all
Pods" in every namespace, or "read Pods in `staging`" only — the namespace
comes from the binding, not from the role.

## Use it for

- Permissions that span namespaces, such as reading Pods everywhere for a
  monitoring agent.
- Cluster-scoped resources — nodes, persistent volumes, namespaces — which a
  namespaced [Role](/form?apiVersion=rbac.authorization.k8s.io/v1&kind=Role)
  cannot grant at all.

## Use something else for

- Permissions confined to one namespace →
  [Role](/form?apiVersion=rbac.authorization.k8s.io/v1&kind=Role)
- The built-in aggregate roles → `view`, `edit`, `admin`, `cluster-admin`.

## Watch out for

`cluster-admin` is a `*` on `*` on `*`, bound cluster-wide. It can read every
Secret in every namespace, which means every credential in the cluster. It is
the right answer surprisingly rarely.

The second is aggregation. The built-in `view` role is not one object — it is
an aggregate, and its rules are assembled from other roles labelled
`rbac.authorization.k8s.io/aggregate-to-view: "true"`. A custom role with that
label joins the aggregate, which can quietly widen `view` for everyone.

The third, as with a Role: a rule with an empty resource or verb list grants
nothing, silently.
